# Global Season: one Season row per crop_year; farms link via FarmSeasonAssociation.

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def forwards_consolidate_seasons(apps, schema_editor):
    connection = schema_editor.connection
    season_table = "seasons_season"
    assoc_table = "seasons_farm_association"
    lot_table = "lots_lot"

    with connection.cursor() as cursor:
        cols = {
            c.name
            for c in connection.introspection.get_table_description(cursor, season_table)
        }
        has_farm = "farm_id" in cols
        has_farmer_accepted = "farmer_accepted" in cols
        has_farmer_accepted_at = "farmer_accepted_at" in cols

        cursor.execute(
            f"""
            SELECT id, crop_year, created_at
            {", farm_id" if has_farm else ""}
            {", farmer_accepted" if has_farmer_accepted else ""}
            {", farmer_accepted_at" if has_farmer_accepted_at else ""}
            FROM {season_table}
            ORDER BY crop_year, created_at, id
            """
        )
        rows = cursor.fetchall()

        by_year = {}
        for row in rows:
            idx = 0
            season_id = row[idx]
            idx += 1
            crop_year = row[idx]
            idx += 1
            _created_at = row[idx]
            idx += 1
            farm_id = row[idx] if has_farm else None
            if has_farm:
                idx += 1
            farmer_accepted = bool(row[idx]) if has_farmer_accepted else False
            if has_farmer_accepted:
                idx += 1
            farmer_accepted_at = row[idx] if has_farmer_accepted_at else None

            canonical_id = by_year.setdefault(crop_year, season_id)

            if has_farm and farm_id is not None:
                cursor.execute(
                    f"""
                    INSERT INTO {assoc_table}
                        (id, created_at, updated_at, farmer_accepted, farmer_accepted_at, accepted_by_id, farm_id, season_id)
                    VALUES
                        (%s, NOW(), NOW(), %s, %s, NULL, %s, %s)
                    ON CONFLICT (farm_id, season_id) DO UPDATE SET
                        farmer_accepted = {assoc_table}.farmer_accepted OR EXCLUDED.farmer_accepted,
                        farmer_accepted_at = COALESCE({assoc_table}.farmer_accepted_at, EXCLUDED.farmer_accepted_at),
                        updated_at = NOW()
                    """,
                    [str(uuid.uuid4()), farmer_accepted, farmer_accepted_at, farm_id, canonical_id],
                )

            if season_id != canonical_id:
                cursor.execute(
                    f"UPDATE {lot_table} SET season_id = %s WHERE season_id = %s",
                    [canonical_id, season_id],
                )
                cursor.execute(
                    f"DELETE FROM {season_table} WHERE id = %s",
                    [season_id],
                )


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("farms", "0002_farm_geofence_geojson"),
        ("lots", "0002_lot_farm"),
        ("seasons", "0002_season_farmer_acceptance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    CREATE TABLE IF NOT EXISTS seasons_farm_association (
                        id uuid PRIMARY KEY,
                        created_at timestamp with time zone NOT NULL,
                        updated_at timestamp with time zone NOT NULL,
                        farmer_accepted boolean NOT NULL DEFAULT false,
                        farmer_accepted_at timestamp with time zone NULL,
                        accepted_by_id uuid NULL REFERENCES accounts_user(id) ON DELETE SET NULL,
                        farm_id uuid NOT NULL REFERENCES farms_farm(id) ON DELETE CASCADE,
                        season_id uuid NOT NULL REFERENCES seasons_season(id) ON DELETE CASCADE,
                        UNIQUE (farm_id, season_id)
                    );
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name="FarmSeasonAssociation",
                    fields=[
                        (
                            "id",
                            models.UUIDField(
                                default=uuid.uuid4,
                                editable=False,
                                primary_key=True,
                                serialize=False,
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("farmer_accepted", models.BooleanField(default=False)),
                        ("farmer_accepted_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "accepted_by",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="accepted_farm_season_associations",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "farm",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="season_associations",
                                to="farms.farm",
                            ),
                        ),
                        (
                            "season",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="farm_associations",
                                to="seasons.season",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "seasons_farm_association",
                        "ordering": ["-created_at"],
                        "unique_together": {("farm", "season")},
                    },
                ),
            ],
        ),
        migrations.RunPython(forwards_consolidate_seasons, backwards_noop, atomic=False),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE seasons_season DROP COLUMN IF EXISTS farmer_accepted CASCADE;",
                    reverse_sql=migrations.RunSQL.noop,
                )
            ],
            state_operations=[
                migrations.RemoveField(model_name="season", name="farmer_accepted"),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE seasons_season DROP COLUMN IF EXISTS farmer_accepted_at CASCADE;",
                    reverse_sql=migrations.RunSQL.noop,
                )
            ],
            state_operations=[
                migrations.RemoveField(model_name="season", name="farmer_accepted_at"),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE seasons_season DROP COLUMN IF EXISTS farm_id CASCADE;",
                    reverse_sql=migrations.RunSQL.noop,
                )
            ],
            state_operations=[
                migrations.AlterUniqueTogether(
                    name="season",
                    unique_together=set(),
                ),
                migrations.RemoveField(model_name="season", name="farm"),
                migrations.AlterField(
                    model_name="season",
                    name="crop_year",
                    field=models.PositiveIntegerField(db_index=True, unique=True),
                ),
            ],
        ),
    ]
