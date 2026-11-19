import type { ReactElement } from "react";
import { initials } from "../../people";
import type { TeamMember } from "../../team";

/**
 * A person's picture, or their initials until they add one.
 *
 * The initials tile is the same shape as a photo, so a row of cards holds its
 * grid whether or not everyone has uploaded a picture yet.
 */
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
