"""
Farm registration workflow via WhatsApp.

States:
  INIT -> ASK_NAME -> ASK_DISTRICT -> ASK_LOCATION -> ASK_SIZE ->
  ASK_VARIETY -> ASK_SEASON -> CONFIRM -> DONE
"""
import logging
from datetime import date

from django.db import transaction

from apps.common.enums import SeasonStatus
from apps.whatsapp.session_service import advance_state, end_conversation
from apps.whatsapp.workflows.base import BaseWorkflow, Reply

logger = logging.getLogger(__name__)


class FarmRegistrationWorkflow(BaseWorkflow):

    def get_name(self) -> str:
        return "farm_registration"

    def handle_init(self, conv, body, contact):
        if not contact.user:
            end_conversation(conv)
            return Reply("You must be registered first. Type REGISTER to create an account.", end_conversation=True)
        advance_state(conv, "ASK_NAME")
        return Reply("Let's register your farm. What is the farm name?")

    def handle_ask_name(self, conv, body, contact):
        name = body.strip()
        if len(name) < 2:
            return Reply("Please enter a valid farm name:")
        advance_state(conv, "ASK_DISTRICT", {"farm_name": name.title()})
        return Reply(f"Farm: {name.title()}\nWhich district is this farm in?")

    def handle_ask_district(self, conv, body, contact):
        district = body.strip().title()
        if len(district) < 2:
            return Reply("Please enter a valid district:")
        advance_state(conv, "ASK_LOCATION", {"district": district})
        return Reply("Enter location description (nearest landmark, village):")

    def handle_ask_location(self, conv, body, contact):
        location = body.strip()
        advance_state(conv, "ASK_SIZE", {"location": location})
        return Reply("What is the farm size in hectares? (e.g. 2.5)")

    def handle_ask_size(self, conv, body, contact):
        try:
            size = float(body.strip())
            if size <= 0 or size > 50000:
                raise ValueError
        except ValueError:
            return Reply("Please enter a valid number of hectares (e.g. 2.5):")

        advance_state(conv, "ASK_VARIETY", {"size_hectares": size})
        return Reply(
            "What tobacco variety do you grow?\n"
            "1. Virginia Flue-Cured\n"
            "2. Burley\n"
            "3. Oriental\n"
            "4. Dark Air-Cured\n"
            "5. Other"
        )

    def handle_ask_variety(self, conv, body, contact):
        varieties = {
            1: "Virginia Flue-Cured",
            2: "Burley",
            3: "Oriental",
            4: "Dark Air-Cured",
            5: "Other",
        }
        choice = self._parse_choice(body, 5)
        if not choice:
            v = body.strip().title()
            if len(v) >= 2:
                advance_state(conv, "ASK_SEASON", {"variety": v})
            else:
                return Reply("Please choose 1-5 or type the variety name:")
        else:
            advance_state(conv, "ASK_SEASON", {"variety": varieties[choice]})

        return Reply(
            "Would you like to create a season for this farm now?\n"
            "1. Yes\n"
            "2. No, just register the farm"
        )

    def handle_ask_season(self, conv, body, contact):
        choice = self._parse_choice(body, 2)
        if choice == 1:
            advance_state(conv, "ASK_CROP_YEAR", {"create_season": True})
            return Reply(f"Enter the crop year (e.g. {date.today().year}):")
        elif choice == 2:
            advance_state(conv, "CONFIRM", {"create_season": False})
            return self._show_confirmation(conv)
        return Reply("Please choose 1 or 2:")

    def handle_ask_crop_year(self, conv, body, contact):
        try:
            year = int(body.strip())
            if year < 2020 or year > 2035:
                raise ValueError
        except ValueError:
            return Reply("Enter a valid year (e.g. 2026):")
        advance_state(conv, "CONFIRM", {"crop_year": year})
        return self._show_confirmation(conv)

    def _show_confirmation(self, conv) -> Reply:
        d = conv.state_data
        lines = [
            "Please confirm your farm details:\n",
            f"Farm: {d.get('farm_name')}",
            f"District: {d.get('district')}",
            f"Location: {d.get('location', 'N/A')}",
            f"Size: {d.get('size_hectares')} ha",
            f"Variety: {d.get('variety', 'N/A')}",
        ]
        if d.get("create_season"):
            lines.append(f"Season: {d.get('crop_year')}")
        lines.append("\nReply YES to confirm or NO to cancel.")
        return Reply("\n".join(lines))

    def handle_confirm(self, conv, body, contact):
        if body.strip().lower() not in ("yes", "y"):
            end_conversation(conv)
            return Reply("Farm registration cancelled.", end_conversation=True)

        d = conv.state_data
        user = contact.user

        with transaction.atomic():
            from apps.farms.models import Farm
            farm = Farm.objects.create(
                owner=user,
                name=d["farm_name"],
                district=d.get("district", ""),
                location_description=d.get("location", ""),
                size_hectares=d.get("size_hectares"),
            )

            season = None
            if d.get("create_season"):
                from apps.seasons.models import Season
                season = Season.objects.create(
                    farm=farm,
                    crop_year=d["crop_year"],
                    name=f"{d['farm_name']} {d['crop_year']}",
                    status=SeasonStatus.PLANNING,
                )

        from apps.audit.services import log_audit
        log_audit(
            actor=user,
            action="WHATSAPP_FARM_REGISTRATION",
            resource_type="Farm",
            resource_id=str(farm.id),
            description=f"Farm '{farm.name}' registered via WhatsApp",
        )

        reply_lines = [
            f"Farm '{farm.name}' registered successfully!",
            f"Farm ID: {str(farm.id)[:8]}...",
        ]
        if season:
            reply_lines.append(f"Season {season.crop_year} created.")
        reply_lines.append("\nType CREATE LOT to add lots, or HELP for all commands.")

        end_conversation(conv)
        return Reply("\n".join(reply_lines), end_conversation=True)
