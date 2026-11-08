from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Attachment


@receiver(post_delete, sender=Attachment)
def delete_attachment_file(sender, instance: Attachment, **kwargs) -> None:  # type: ignore[no-untyped-def]
    # Cascade deletes (project/account/admin) use this too; rollbacks retain their files.
    storage, name = instance.file.storage, instance.file.name
    transaction.on_commit(lambda: storage.delete(name))
