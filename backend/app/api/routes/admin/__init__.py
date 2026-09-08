"""Administration endpoints, split by the thing they administer.

The modules share one router. They are imported for their side effect of
registering routes on it, and the route functions are re-exported because the
tests call them directly rather than through HTTP.
"""

from app.api.routes.admin._common import router
from app.api.routes.admin.publications import (
    PublishRequest,
    get_publication_status,
    publish_round_request,
    retry_publication,
    unpublish_round_request,
)
from app.api.routes.admin.rounds import (
    RoundCreate,
    RoundMemberUpdate,
    RoundUpdate,
    add_round_member,
    create_round,
    get_round_for_administration,
    remove_round_member,
    update_round,
)
from app.api.routes.admin.series import (
    GroupCreate,
    InviteCreate,
    PlaylistImportRequest,
    SeriesCreate,
    SeriesUpdate,
    add_group_member,
    add_series_admin,
    add_series_member,
    create_group,
    create_series,
    create_series_invite,
    get_series_for_administration,
    import_spotify_playlist,
    list_series_for_administration,
    list_series_members,
    remove_series_member,
    search_users_for_series,
    update_series,
)

__all__ = [
    "GroupCreate",
    "InviteCreate",
    "PlaylistImportRequest",
    "PublishRequest",
    "RoundCreate",
    "RoundMemberUpdate",
    "RoundUpdate",
    "SeriesCreate",
    "SeriesUpdate",
    "add_group_member",
    "add_round_member",
    "add_series_admin",
    "add_series_member",
    "create_group",
    "create_round",
    "create_series",
    "create_series_invite",
    "get_publication_status",
    "get_round_for_administration",
    "get_series_for_administration",
    "import_spotify_playlist",
    "list_series_for_administration",
    "list_series_members",
    "publish_round_request",
    "remove_round_member",
    "remove_series_member",
    "retry_publication",
    "router",
    "search_users_for_series",
    "unpublish_round_request",
    "update_round",
    "update_series",
]
