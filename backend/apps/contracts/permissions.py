from rest_framework.permissions import SAFE_METHODS, BasePermission


class ReadOnlyOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or request.user.is_staff


class IsOwnerOrStaff(BasePermission):
    def has_object_permission(self, request, view, obj):
        owner_id = getattr(obj, "owner_id", None)
        if owner_id is None and hasattr(obj, "contract"):
            owner_id = obj.contract.owner_id
        return request.user.is_staff or owner_id == request.user.pk
