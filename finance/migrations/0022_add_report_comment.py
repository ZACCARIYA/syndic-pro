# Generated manually

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0021_auto_20250927_1752'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReportComment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('comment', models.TextField(verbose_name='Commentaire')),
                ('is_internal', models.BooleanField(default=False, verbose_name='Commentaire interne')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Date de création')),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='report_comments', to='accounts.user')),
                ('report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='finance.residentreport')),
            ],
            options={
                'verbose_name': 'Commentaire de rapport',
                'verbose_name_plural': 'Commentaires de rapports',
                'ordering': ['created_at'],
            },
        ),
    ]
