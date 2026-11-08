# WalkInPass becomes Visit: every way in (kiosk/staff walk-in, invitation, intercom) records a visit.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_walk_in_passes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel("WalkInPass", "Visit"),
        migrations.RenameIndex(model_name="visit", new_name="core_visit_condomi_37c943_idx",
                               old_name="core_walkin_condomi_2d3561_idx"),
        migrations.AlterField(
            model_name="visit", name="condominium",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="visits", to="core.condominium"),
        ),
        migrations.AlterField(
            model_name="visit", name="unit",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="visits", to="core.unit"),
        ),
        migrations.AlterField(
            model_name="visit", name="kiosk",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="visits", to="core.kiosk"),
        ),
        migrations.AlterField(
            model_name="visit", name="visitor",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="visits", to="core.visitor"),
        ),
        migrations.AlterField(
            model_name="visit", name="checked_out_by",
            field=models.ForeignKey(blank=True, help_text="Staff member who checked the visitor out; empty when they scanned out or drove out.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="visit", name="source",
            field=models.CharField(choices=[("kiosk", "Walk-in (kiosk)"), ("staff", "Walk-in (security)"), ("invitation", "Invitation"), ("intercom", "Intercom")], default="kiosk", max_length=20),
        ),
        migrations.AddField(
            model_name="visit", name="gate",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="visits", to="core.accessgate"),
        ),
        migrations.AddField(
            model_name="visit", name="invitation",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="visits", to="core.invitation"),
        ),
        migrations.AddField(
            model_name="visit", name="intercom_call",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="visits", to="core.intercomcall"),
        ),
        migrations.AddField(
            model_name="visit", name="entry_log",
            field=models.ForeignKey(blank=True, help_text="The access-log entry that let the visitor in (its photo is shown when the visit has none).", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="core.accesslog"),
        ),
        migrations.AddField(
            model_name="visit", name="vehicle_plate",
            field=models.CharField(blank=True, max_length=12),
        ),
        migrations.AddField(
            model_name="visit", name="notes",
            field=models.TextField(blank=True, help_text="Security's notes, e.g. items carried or vehicle parked."),
        ),
        migrations.AddField(
            model_name="visit", name="created_by",
            field=models.ForeignKey(blank=True, help_text="Security staff who registered the walk-in.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL),
        ),
    ]
