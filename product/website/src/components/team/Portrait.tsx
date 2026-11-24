import type { ReactElement } from "react";
import { initials } from "../../people";
import type { TeamMember } from "../../team";

export const Portrait = ({
  bust = false,
  eager = false,
  member,
}: {
  /** Head and chest rather than the whole photograph. */
  bust?: boolean;
  /** The profile's own portrait is the page's picture; cards load lazily. */
  eager?: boolean;
  member: TeamMember;
}): ReactElement =>
  member.photo ? (
    <img
      alt=""
      className="gr-portrait"
      loading={eager ? "eager" : "lazy"}
      src={bust ? member.photo.bust : member.photo.src}
    />
  ) : (
    <span aria-hidden="true" className="gr-portrait gr-portrait--initials">
      {initials(member.name.replace(/^Dr\s+/, ""))}
    </span>
  );
