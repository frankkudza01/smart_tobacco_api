"""
WhatsApp end-to-end smoke test for quick operational validation.

Usage:
    python manage.py whatsapp_smoke_test
    python manage.py whatsapp_smoke_test --no-strict
    python manage.py whatsapp_smoke_test --send-live-to +2637XXXXXXX
"""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.common.enums import UserRole
from apps.whatsapp.intent_router import route_inbound_message
from apps.whatsapp.twilio_service import get_whatsapp_provider, send_whatsapp_message


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


class Command(BaseCommand):
    help = "Run WhatsApp channel smoke tests (config, routes, routing, optional live send)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--farmer-phone",
            default="+263771234567",
            help="Phone to simulate farmer messages.",
        )
        parser.add_argument(
            "--buyer-phone",
            default="+263772345678",
            help="Phone to simulate buyer messages.",
        )
        parser.add_argument(
            "--skip-routing",
            action="store_true",
            help="Skip intent-routing simulations and only run config/URL checks.",
        )
        parser.add_argument(
            "--send-live-to",
            default="",
            help="Optional phone to send one live outbound message through current provider.",
        )
        parser.add_argument(
            "--send-live-message",
            default="WhatsApp smoke test from Zimbabwe Tobacco Platform backend.",
            help="Custom live test message body.",
        )
        parser.add_argument(
            "--no-strict",
            action="store_true",
            help="Do not fail command exit code when checks fail.",
        )

    def handle(self, *args, **options):
        results: list[CheckResult] = []
        strict = not options["no_strict"]

        results.extend(self._run_configuration_checks())
        results.extend(self._run_url_checks())

        if not options["skip_routing"]:
            results.extend(
                self._run_routing_checks(
                    farmer_phone=options["farmer_phone"],
                    buyer_phone=options["buyer_phone"],
                )
            )

        send_live_to = (options["send_live_to"] or "").strip()
        if send_live_to:
            results.append(
                self._run_live_send_check(
                    to=send_live_to,
                    message=options["send_live_message"],
                )
            )

        failures = [r for r in results if not r.ok]
        passes = [r for r in results if r.ok]

        self.stdout.write("")
        self.stdout.write("WhatsApp Smoke Test Results")
        self.stdout.write("-" * 40)
        for r in results:
            tag = self.style.SUCCESS("PASS") if r.ok else self.style.ERROR("FAIL")
            self.stdout.write(f"[{tag}] {r.name}: {r.detail}")

        self.stdout.write("-" * 40)
        self.stdout.write(f"Passed: {len(passes)}")
        self.stdout.write(f"Failed: {len(failures)}")

        if failures and strict:
            raise CommandError("WhatsApp smoke test failed.")

        if failures:
            self.stdout.write(self.style.WARNING("Completed with failures (non-strict mode)."))
        else:
            self.stdout.write(self.style.SUCCESS("All WhatsApp smoke checks passed."))

    def _run_configuration_checks(self) -> list[CheckResult]:
        mode = str(getattr(settings, "WHATSAPP_WEBHOOK_REPLY_MODE", "sync")).lower()
        provider = get_whatsapp_provider()
        provider_name = provider.__class__.__name__
        configured_mode = str(getattr(settings, "WHATSAPP_PROVIDER", "auto")).lower()
        waapi_instance = str(getattr(settings, "WAAPI_INSTANCE_ID", "")).strip()
        waapi_token = bool(getattr(settings, "WAAPI_TOKEN", ""))
        twilio_sid = bool(getattr(settings, "TWILIO_ACCOUNT_SID", ""))
        twilio_token = bool(getattr(settings, "TWILIO_AUTH_TOKEN", ""))

        checks = [
            CheckResult(
                name="reply-mode",
                ok=mode in {"sync", "async"},
                detail=f"WHATSAPP_WEBHOOK_REPLY_MODE={mode}",
            ),
            CheckResult(
                name="provider-resolution",
                ok=True,
                detail=f"WHATSAPP_PROVIDER={configured_mode}, resolved={provider_name}",
            ),
            CheckResult(
                name="provider-credentials",
                ok=(waapi_instance and waapi_token) or (twilio_sid and twilio_token),
                detail="WaAPI or Twilio credentials are configured",
            ),
        ]
        return checks

    def _run_url_checks(self) -> list[CheckResult]:
        try:
            webhook_url = reverse("whatsapp-webhook")
            webhook_ok = True
            webhook_detail = webhook_url
        except Exception as exc:
            webhook_ok = False
            webhook_detail = f"reverse failed: {exc}"

        try:
            status_url = reverse("whatsapp-delivery-status")
            status_ok = True
            status_detail = status_url
        except Exception as exc:
            status_ok = False
            status_detail = f"reverse failed: {exc}"

        return [
            CheckResult("webhook-url", webhook_ok, webhook_detail),
            CheckResult("status-url", status_ok, status_detail),
        ]

    def _run_routing_checks(self, *, farmer_phone: str, buyer_phone: str) -> list[CheckResult]:
        checks: list[CheckResult] = []
        checks.append(self._route_case("help-menu-farmer", farmer_phone, "help", must_include="Commands"))
        checks.append(self._route_case("lookup-settlements", farmer_phone, "my settlements"))
        checks.append(self._route_case("help-menu-buyer", buyer_phone, "help", must_include="Commands"))

        # Validate role-aware command visibility when sample users are available.
        from django.contrib.auth import get_user_model
        User = get_user_model()
        buyer_user = User.objects.filter(phone_number=buyer_phone, role=UserRole.BUYER_CONTRACTOR).first()
        if buyer_user:
            checks.append(
                self._route_case(
                    "buyer-ops-command",
                    buyer_phone,
                    "record sale",
                    must_include="select",
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="buyer-ops-command",
                    ok=True,
                    detail="skipped (no buyer mapped to supplied buyer phone)",
                )
            )
        return checks

    def _route_case(self, name: str, phone: str, text: str, must_include: str = "") -> CheckResult:
        try:
            response = route_inbound_message(phone, text)
        except Exception as exc:
            return CheckResult(name=name, ok=False, detail=f"routing exception: {exc}")

        if not isinstance(response, str) or not response.strip():
            return CheckResult(name=name, ok=False, detail="empty response")

        if must_include and must_include.lower() not in response.lower():
            preview = response[:120].replace("\n", " ")
            return CheckResult(
                name=name,
                ok=False,
                detail=f"missing expected text '{must_include}' (got: {preview})",
            )

        preview = response[:100].replace("\n", " ")
        return CheckResult(name=name, ok=True, detail=f"response ok: {preview}")

    def _run_live_send_check(self, *, to: str, message: str) -> CheckResult:
        try:
            log = send_whatsapp_message(to=to, body=message)
        except Exception as exc:
            return CheckResult("live-send", False, f"send exception: {exc}")

        ok = str(log.delivery_status).upper() != "FAILED"
        detail = f"status={log.delivery_status}, provider_message_id={log.provider_message_id or 'n/a'}"
        return CheckResult("live-send", ok, detail)
