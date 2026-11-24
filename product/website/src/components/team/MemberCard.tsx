import type { ReactElement } from "react";
import type { TeamMember } from "../../team";
import { Portrait } from "./Portrait";

/** One person in a row of people. The whole card is the link to their page. */
export const MemberCard = ({
  detail = "place",
  member,
}: {
  /** What sits under the role: where they are based, their summary, or nothing. */
  detail?: "none" | "place" | "summary";
  member: TeamMember;
}): ReactElement => (
  <a className="gr-member" href={member.path}>
    <span className="gr-member-frame">
      <Portrait member={member} />
    </span>
    <span className="gr-member-name">{member.name}</span>
    <span className="gr-member-role">{member.role}</span>
    {detail === "summary" && member.summary ? (
      <span className="gr-member-summary">{member.summary}</span>
    ) : null}
    {detail === "place" && member.location ? (
      <span className="gr-member-place">
        {member.location.city}, {member.location.country}
      </span>
    ) : null}
  </a>
);

export const MemberGrid = ({
  className,
  detail,
  members,
}: {
  className?: string;
  detail?: "none" | "place" | "summary";
  members: TeamMember[];
}): ReactElement => (
  <ul className={["gr-member-grid", className].filter(Boolean).join(" ")}>
    {members.map((member) => (
      <li key={member.slug}>
        <MemberCard detail={detail} member={member} />
      </li>
    ))}
  </ul>
);
