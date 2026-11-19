import { useId, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import {
  findPerson,
  findTeam,
  initials,
  teamMembers,
  teams,
} from "../../people";
import type { Person as PersonRecord } from "../../people";

const Avatar = ({ person }: { person: PersonRecord }): ReactElement =>
  person.photo ? (
    <img
      alt=""
      className="gr-pill__avatar"
      height={20}
      src={person.photo}
      width={20}
    />
  ) : (
    <span aria-hidden="true" className="gr-pill__avatar">
      {initials(person.name)}
    </span>
  );

const Pill = ({
  card,
  children,
  href,
}: {
  card: ReactNode;
  children: ReactNode;
  href?: string;
}): ReactElement => {
  const id = useId();
  const wrapRef = useRef<HTMLSpanElement>(null);
  const cardRef = useRef<HTMLSpanElement>(null);
  const [shift, setShift] = useState(0);

  const place = () => {
    const wrap = wrapRef.current;
    const tip = cardRef.current;
    if (!wrap || !tip) return;

    const gutter = 16;
    const left = wrap.getBoundingClientRect().left;
    const overflow =
      left + tip.offsetWidth - (document.documentElement.clientWidth - gutter);
    setShift(Math.min(0, Math.max(-overflow, gutter - left)));
  };

  const tip = card ? (
    <span
      className="gr-pill__card"
      id={id}
      ref={cardRef}
      role="tooltip"
      style={{ insetInlineStart: shift }}
    >
      {card}
    </span>
  ) : null;
  const describedBy = card ? id : undefined;

  return (
    <span
      className="gr-pill-wrap"
      onFocus={place}
      onMouseEnter={place}
      ref={wrapRef}
    >
      {href ? (
        <a aria-describedby={describedBy} className="gr-pill" href={href}>
          {children}
        </a>
      ) : (
        <span
          aria-describedby={describedBy}
          className="gr-pill"
          tabIndex={card ? 0 : undefined}
        >
          {children}
        </span>
      )}
      {tip}
    </span>
  );
};

const teamNames = (person: PersonRecord): string =>
  (person.teams ?? [])
    .map((slug) => teams.find((team) => team.slug === slug)?.name ?? slug)
    .join(", ");

export const Person = ({ name }: { name: string }): ReactElement => {
  const person = findPerson(name);
  const team = teamNames(person);

  return (
    <Pill
      card={
        person.role || team ? (
          <>
            {person.role ? <span>{person.role}</span> : null}
            {team ? <span className="gr-pill__card-muted">{team}</span> : null}
          </>
        ) : null
      }
      href={person.href}
    >
      <Avatar person={person} />
      <span className="gr-pill__name">{person.name}</span>
    </Pill>
  );
};

export const Team = ({ slug }: { slug: string }): ReactElement => {
  const team = findTeam(slug);
  const members = teamMembers(slug);

  return (
    <Pill
      card={
        members.length > 0 ? (
          <>
            {members.map((member) => (
              <span key={member.name}>
                {member.name}
                {member.role ? (
                  <span className="gr-pill__card-muted"> - {member.role}</span>
                ) : null}
              </span>
            ))}
          </>
        ) : null
      }
    >
      {members.length > 0 ? (
        <span className="gr-pill__stack">
          {members.slice(0, 3).map((member) => (
            <Avatar key={member.name} person={member} />
          ))}
        </span>
      ) : null}
      <span className="gr-pill__name">{team.name}</span>
    </Pill>
  );
};
