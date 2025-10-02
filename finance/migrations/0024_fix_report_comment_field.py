# Generated manually to fix column name mismatch

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0023_auto_20250928_0614'),
    ]

    operations = [
        migrations.RunSQL(
            "ALTER TABLE finance_reportcomment RENAME COLUMN content TO comment;",
            reverse_sql="ALTER TABLE finance_reportcomment RENAME COLUMN comment TO content;"
        ),
    ]
