from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import Profile

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """ Cria um Profile automaticamente sempre que um User é criado. """
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """ Salva o Profile automaticamente sempre que um User é salvo. """
    try:
        instance.profile.save()
    except Profile.DoesNotExist:
        # Caso o usuário tenha sido criado antes do signal existir
        Profile.objects.create(user=instance)