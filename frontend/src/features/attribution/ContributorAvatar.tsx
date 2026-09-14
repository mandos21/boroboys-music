import type { components } from "../../api/schema";
import { avatarStyle } from "../../lib/avatar";

type Contributor = components["schemas"]["ContributorResponse"];

export function ContributorAvatar({ member }: { member: Contributor }) {
  return member.spotifyProfileImageUrl ? (
    <img className="contributor-avatar" src={member.spotifyProfileImageUrl} alt="" />
  ) : (
    <span
      className="contributor-avatar contributor-avatar-fallback"
      style={avatarStyle(member.displayName)}
      aria-hidden="true"
    >
      {member.displayName.slice(0, 1).toUpperCase()}
    </span>
  );
}
