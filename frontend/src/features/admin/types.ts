import type { components } from "../../api/schema";

/** The administration API is generated like the rest of the contract, so these
 * are aliases rather than a second, hand-maintained copy of the same shapes. */
export type Session = { user: { platformRole: string } };

export type Series = components["schemas"]["AdminSeriesResponse"];
export type User = components["schemas"]["AdminUserResponse"];
export type Group = components["schemas"]["AdminGroupResponse"];
export type Round = components["schemas"]["AdminRoundResponse"];
export type SeriesDetail = components["schemas"]["AdminSeriesDetailResponse"];
export type RoundMember = components["schemas"]["AdminRoundMemberResponse"];
export type AdminRound = components["schemas"]["AdminRoundDetailResponse"];
export type Connection = components["schemas"]["ConnectionResponse"];
export type Publication = components["schemas"]["AdminPublicationResponse"];
export type PublicationCommand = components["schemas"]["AdminPublicationCommandResponse"];
