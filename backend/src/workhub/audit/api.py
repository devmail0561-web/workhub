"""API publique du module audit.

Seul point d'entrée autorisé pour les autres modules (règle §3.3-3).
"""

from workhub.audit.application.ports import AuditRecorder
from workhub.audit.domain.audit_entry import AuditEntry, Outcome, PrincipalType

__all__ = ["AuditEntry", "AuditRecorder", "Outcome", "PrincipalType"]
