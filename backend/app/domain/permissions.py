from app.models.enums import Role

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {"*"},
    Role.ENGINEER: {
        "incident:create",
        "incident:read",
        "incident:update",
        "incident:assign",
        "incident:resolve",
        "service:create",
        "service:update",
        "alert:read",
        "alert:update",
        "log:read",
        "runbook:read",
        "postmortem:create",
    },
    Role.ON_CALL_ENGINEER: {
        "incident:read",
        "incident:update",
        "incident:assign",
        "incident:resolve",
        "alert:read",
        "alert:update",
        "log:read",
        "runbook:read",
    },
    Role.VIEWER: {"incident:read", "alert:read", "log:read", "runbook:read"},
}


def has_permission(role: Role, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS[role]
    return "*" in permissions or permission in permissions
