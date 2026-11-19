import { useEffect, useRef } from "react";
import type { ReactElement } from "react";
import { resolveColor, useThemeVersion } from "../../lib/theme-color";
import hiring from "../../hiring-countries.generated.json";

type Reason = "sanctions" | "high-cost" | "contractors" | "timezone";

const reasons: Array<{ key: Reason | "hire"; label: string; tip: string }> = [
  {
    key: "hire",
    label: "Remote roles can be based here",
    tip: "Remote roles can be based here",
  },
  {
    key: "contractors",
    label: "Contractors only",
    tip: "We hire here as contractors only",
  },
  {
    key: "sanctions",
    label: "US sanctions",
    tip: "Restricted by US sanctions",
  },
  {
    key: "high-cost",
    label: "High employer costs",
    tip: "Employer costs are too high",
  },
  {
    key: "timezone",
    label: "Outside our time zones",
    tip: "Outside the time zones we hire in",
  },
];

const swatches: Record<Reason | "hire", string> = {
  hire: "--color-interactive-fill",
  contractors: "--color-aegean-500",
  sanctions: "--color-kiln-500",
  "high-cost": "--color-plum-500",
  timezone: "--color-rule",
};

const restricted = reasons
  .filter((reason) => reason.key !== "contractors")
  .flatMap((reason) => {
    const countries = hiring.countries
      .filter((country) => country.reason === reason.key)
      .map((country) => country.name);

    return countries.length > 0 ? [{ ...reason, countries }] : [];
  });

const contractorCountries = hiring.countries
  .filter((country) => country.reason === "contractors")
  .map((country) => country.name);

const restrictions = new Map(
  hiring.countries.map((country) => [country.code, country.reason as Reason]),
);

export const CountriesWeHireIn = (): ReactElement => {
  const chartRef = useRef<HTMLDivElement>(null);
  const theme = useThemeVersion();

  useEffect(() => {
    const host = chartRef.current;
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

      // No licence key (PostHog's is theirs), so amCharts shows its credit.
      const root = am5.Root.new(host);
      dispose = () => root.dispose();
      // On touch screens, swipes scroll the page until the globe is tapped.
      root.tapToActivate = true;

      if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        root.setThemes([animated.default.new(root)]);
      }

      const chart = root.container.children.push(
        am5map.MapChart.new(root, {
          projection: am5map.geoOrthographic(),
          panX: "rotateX",
          panY: "rotateY",
          wheelY: "none",
          homeGeoPoint: { latitude: 20, longitude: 0 },
          zoomLevel: 1,
        }),
      );

      const zoom = chart.set("zoomControl", am5map.ZoomControl.new(root, {}));

      for (const button of [zoom.plusButton, zoom.minusButton]) {
        // The globe is aria-hidden, so its controls must stay out of the tab order.
        button.set("focusable", false);
        button.get("background")?.setAll({
          fill: color("--color-panel"),
          stroke: color("--color-rule"),
          strokeWidth: 1,
        });
        button.get("background")?.states.create("hover", {
          fill: color("--color-module"),
        });
        button.get("icon")?.set("stroke", color("--color-text"));
      }

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

      const tooltip = am5.Tooltip.new(root, {
        autoTextColor: false,
        getFillFromSprite: false,
        getStrokeFromSprite: false,
        pointerOrientation: "vertical",
      });
      tooltip.get("background")?.setAll({
        fill: color("--color-panel"),
        fillOpacity: 1,
        stroke: color("--color-rule"),
        strokeWidth: 1,
      });
      tooltip.label.setAll({ fill: color("--color-text") });
      countries.set("tooltip", tooltip);

      const fills = Object.fromEntries(
        Object.entries(swatches).map(([key, property]) => [
          key,
          color(property),
        ]),
      ) as Record<Reason | "hire", ReturnType<typeof am5.color>>;

      const reasonOf = (target: { dataItem?: unknown }) => {
        const context = (target.dataItem as { dataContext?: { id?: string } })
          ?.dataContext;

        return restrictions.get(context?.id ?? "") ?? "hire";
      };

      countries.mapPolygons.template.setAll({
        interactive: true,
        stroke: color("--color-module"),
        strokeWidth: 0.5,
        tooltipText: "{name}",
      });

      // Leave the hover state's fill alone, or the highlight never shows.
      countries.mapPolygons.template.adapters.add("fill", (fill, target) =>
        target.isHover() ? fill : fills[reasonOf(target)],
      );
      countries.mapPolygons.template.adapters.add(
        "tooltipText",
        (_text, target) => {
          const tip = reasons.find(
            (reason) => reason.key === reasonOf(target),
          )?.tip;

          return `[bold]{name}[/]\n${tip}`;
        },
      );
      countries.mapPolygons.template.states.create("hover", {
        fill: color("--color-interactive"),
      });
    });

    return () => {
      disposed = true;
      dispose();
    };
  }, [theme]);

  return (
    <figure className="gr-hiring-map">
      <div aria-hidden="true" className="gr-hiring-map__globe" ref={chartRef} />
      <figcaption>
        <div className="gr-visually-hidden">
          <p>Remote roles can be based in any country except these:</p>
          <ul>
            {restricted.map((group) => (
              <li key={group.key}>
                {group.label}: {group.countries.join(", ")}
              </li>
            ))}
          </ul>
          {contractorCountries.length > 0 ? (
            <p>
              Roles in {new Intl.ListFormat("en").format(contractorCountries)}{" "}
              are for contractors only.
            </p>
          ) : null}
        </div>
        <ul aria-hidden="true" className="gr-hiring-map__legend">
          {reasons.map((reason) => (
            <li key={reason.key}>
              <span
                aria-hidden="true"
                className={`gr-hiring-map__swatch gr-hiring-map__swatch--${reason.key}`}
                style={{ background: `var(${swatches[reason.key]})` }}
              />
              {reason.label}
            </li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
};
