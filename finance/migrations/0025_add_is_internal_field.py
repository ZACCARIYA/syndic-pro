# Generated manually to add missing is_internal field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0024_fix_report_comment_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportcomment',
            name='is_internal',
            field=models.BooleanField(default=False, verbose_name='Commentaire interne'),
        ),
    ]
