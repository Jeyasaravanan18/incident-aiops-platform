from app.domain.permissions import has_permission
from app.models.enums import Role


def test_admin_has_all_permissions() -> None:
    assert has_permission(Role.ADMIN, "incident:delete")


def test_viewer_cannot_mutate_incidents() -> None:
    assert not has_permission(Role.VIEWER, "incident:update")
