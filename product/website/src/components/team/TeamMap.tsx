import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { useNavigate } from "react-router-dom";
import { resolveColor, useThemeVersion } from "../../lib/theme-color";
import type { TeamPlace } from "../../team";

const escape = (text: string): string =>
  text.replace(/[&<>"]/g, (character) => `&#${character.charCodeAt(0)};`);

const radiusOf = (place: TeamPlace): number =>
  14 + Math.min(place.members.length, 8) * 1.5;

/** Cities this close would hide each other's pins, so each is nudged away
    from the others, by its own radius, in the direction they lie. */
const NEIGHBOURS_KM = 300;

const nudgeOf = (place: TeamPlace, places: TeamPlace[]) => {
  let east = 0;
  let north = 0;
  for (const other of places) {
    if (other === place) continue;

    const dNorth = place.latitude - other.latitude;
    const dEast =
      (place.longitude - other.longitude) *
      Math.cos((place.latitude * Math.PI) / 180);
    if (Math.hypot(dNorth, dEast) * 111 > NEIGHBOURS_KM) continue;

    east += dEast;
    north += dNorth;
  }

  const length = Math.hypot(east, north);
  if (!length) return { dx: 0, dy: 0 };

  const reach = radiusOf(place) + 1;
  return { dx: (east / length) * reach, dy: (-north / length) * reach };
};

/**
 * The globe on /team/: one pin per city, sized by how many people are there.
 * Hovering one lists its people, each a link to their page, and a city of
 * one goes straight there. It is decoration: the rail lists everyone, so the
 * globe is aria-hidden and its pins stay out of the tab order.
 */
export const TeamMap = ({
  centre,
  places,
}: {
  /** The point turned to face the reader; the first city when left out. */
  centre?: { latitude: number; longitude: number };
  places: TeamPlace[];
}): ReactElement => {
  const hostRef = useRef<HTMLDivElement>(null);
  const theme = useThemeVersion();
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  // The tooltip's links are plain anchors drawn by amCharts; the router
  // follows them without reloading the page.
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const follow = (event: MouseEvent) => {
      const link = (event.target as Element).closest?.("a[href]");
      if (!link || event.metaKey || event.ctrlKey || event.shiftKey) return;

      event.preventDefault();
      navigateRef.current(link.getAttribute("href") ?? "/team/");
    };
    host.addEventListener("click", follow);

    return () => host.removeEventListener("click", follow);
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let disposed = false;
    let dispose = () => {};

    void Promise.all([
      import("@amcharts/amcharts5"),
      import("@amcharts/amcharts5/map"),
      import("@amcharts/amcharts5-geodata/worldLow"),
      import("@amcharts/amcharts5/themes/Animated"),
    ]).then(([am5, am5map, worldLow, animated]) => {
      if (disposed) return;

      const color = (property: string) =>
        am5.color(resolveColor(host, property));
      const still = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;

      // No licence key (PostHog's is theirs), so amCharts shows its credit.
      const root = am5.Root.new(host);
      dispose = () => root.dispose();
      // On touch screens, swipes scroll the page until the globe is tapped.
      root.tapToActivate = true;
      if (!still) root.setThemes([animated.default.new(root)]);

      const facing = centre ?? places[0];
      const chart = root.container.children.push(
        am5map.MapChart.new(root, {
          projection: am5map.geoOrthographic(),
          panX: "rotateX",
          panY: "rotateY",
          wheelY: "none",
          rotationX: facing ? -facing.longitude : 0,
          rotationY: facing ? -facing.latitude : -20,
          zoomLevel: 1,
        }),
      );

      const ocean = chart.series.unshift(am5map.MapPolygonSeries.new(root, {}));
      ocean.mapPolygons.template.setAll({
        fill: color("--color-module"),
        stroke: color("--color-rule"),
        strokeWidth: 1,
      });
      ocean.data.push({ geometry: am5map.getGeoRectangle(90, 180, -90, -180) });

      const graticule = chart.series.push(am5map.GraticuleSeries.new(root, {}));
      graticule.mapLines.template.setAll({
        stroke: color("--color-text"),
        strokeOpacity: 0.08,
      });

      const countries = chart.series.push(
        am5map.MapPolygonSeries.new(root, { geoJSON: worldLow.default }),
      );
      countries.mapPolygons.template.setAll({
        fill: color("--color-rule"),
        stroke: color("--color-module"),
        strokeWidth: 0.5,
      });

      const tooltip = am5.Tooltip.new(root, {
        autoTextColor: false,
        getFillFromSprite: false,
        getStrokeFromSprite: false,
        keepTargetHover: true,
        pointerOrientation: "down",
      });
      tooltip.get("background")?.setAll({
        fill: color("--color-panel"),
        fillOpacity: 1,
        stroke: color("--color-rule"),
        strokeWidth: 1,
      });
      tooltip.label.setAll({ fill: color("--color-text") });
      const ink = resolveColor(host, "--color-text");

      const pinInk = color("--color-inverse");

      const points = chart.series.push(
        am5map.MapPointSeries.new(root, {
          latitudeField: "latitude",
          longitudeField: "longitude",
        }),
      );
      points.bullets.push((_root, _series, dataItem) => {
        const place = dataItem.dataContext as TeamPlace;
        const people = place.members
          .map(
            (member) =>
              `<a href="${escape(member.path)}" style="color:${ink};text-decoration:underline;text-underline-offset:0.2em">${escape(member.name)}</a>`,
          )
          .join("<br>");
        const pin = am5.Container.new(root, {
          ...nudgeOf(place, places),
          cursorOverStyle: "pointer",
          interactive: true,
          tooltip,
          // Above the pin's top edge, so the card never covers the pin.
          tooltipPosition: "fixed",
          tooltipY: -radiusOf(place) - 2,
          tooltipHTML: `<div style="font:inherit;line-height:1.6"><strong>${escape(place.city)}</strong><br>${people}</div>`,
        });
        if (place.members.length === 1) {
          pin.events.on("click", () =>
            navigateRef.current(place.members[0].path),
          );
        }
        pin.children.push(
          am5.Circle.new(root, {
            radius: radiusOf(place),
            fill: color("--color-interactive"),
            stroke: color("--color-module"),
            strokeWidth: 2,
          }),
        );
        pin.children.push(
          am5.Label.new(root, {
            text: String(place.members.length),
            fill: pinInk,
            fontSize: 15,
            fontWeight: "600",
            centerX: am5.p50,
            centerY: am5.p50,
            paddingTop: 0,
            paddingBottom: 0,
            paddingLeft: 0,
            paddingRight: 0,
          }),
        );
        return am5.Bullet.new(root, { sprite: pin });
      });
      points.data.setAll(places);
    });

    return () => {
      disposed = true;
      dispose();
    };
  }, [centre, places, theme]);

  return <div aria-hidden="true" className="gr-team-map-globe" ref={hostRef} />;
};
