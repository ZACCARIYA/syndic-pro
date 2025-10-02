from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError


class User(AbstractUser):
    class Roles(models.TextChoices):
        SUPERADMIN = "SUPERADMIN", "Super Administrateur"
        SYNDIC = "SYNDIC", "Syndic (Gestionnaire)"
        RESIDENT = "RESIDENT", "Résident"

    role = models.CharField(max_length=20, choices=Roles.choices, default=Roles.RESIDENT)
    apartment = models.CharField(max_length=50, blank=True, help_text="Appartement / Lot")
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    is_resident = models.BooleanField(default=False, help_text="Marque si c'est un résident")
    created_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, 
                                 related_name='created_residents', 
                                 help_text="Utilisateur qui a créé ce compte")

    class Meta:
        constraints = [
            # Ensure one resident per apartment (ignore empty/null apartments)
            models.UniqueConstraint(
                fields=['apartment'],
                condition=(Q(role='RESIDENT') & Q(apartment__isnull=False) & ~Q(apartment='')),
                name='unique_apartment_per_resident',
                violation_error_message="Un résident existe déjà pour cet appartement."
            )
        ]

    def __str__(self) -> str:
        full = self.get_full_name().strip() or self.username
        return f"{full} ({self.apartment})" if self.apartment else full

    def clean(self):
        """Validate the user data"""
        super().clean()
        
        # Check apartment uniqueness for residents
        if self.role == self.Roles.RESIDENT and self.apartment:
            existing_resident = User.objects.filter(
                role=self.Roles.RESIDENT, 
                apartment=self.apartment
            ).exclude(pk=self.pk)
            
            if existing_resident.exists():
                raise ValidationError({
                    'apartment': f'Un résident existe déjà pour l\'appartement {self.apartment}'
                })
    
    def save(self, *args, **kwargs):
        # Auto-set is_resident based on role
        self.is_resident = (self.role == self.Roles.RESIDENT)
        
        # Validate before saving
        self.clean()
        
        super().save(*args, **kwargs)

    @property
    def can_manage_residents(self):
        """Check if user can manage residents"""
        return self.role in [self.Roles.SUPERADMIN, self.Roles.SYNDIC]

    @property
    def can_manage_finances(self):
        """Check if user can manage finances"""
        return self.role in [self.Roles.SUPERADMIN, self.Roles.SYNDIC]

    @property
    def can_send_notifications(self):
        """Check if user can send notifications"""
        return self.role in [self.Roles.SUPERADMIN, self.Roles.SYNDIC]

    @property
    def can_view_own_data_only(self):
        """Check if user can only view their own data"""
        return self.role == self.Roles.RESIDENT
