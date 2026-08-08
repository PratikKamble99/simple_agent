"""Every model must be imported here.

Alembic's autogenerate compares against `Base.metadata`, which is only complete
once each model module has been imported.
"""

from app.models.conversation import Conversation, Message, MessageRole
from app.models.document import Document, DocumentStatus

__all__ = [
    "Conversation",
    "Document",
    "DocumentStatus",
    "Message",
    "MessageRole",
]
