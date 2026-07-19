"use strict";

async function populateYearSelectors() {
  const selectors = [...document.querySelectorAll("select[data-leaders-year]")];
  if (!selectors.length) return;

  const response = await fetch("/reports/leaders/years.json", {cache: "no-store"});
  if (!response.ok) throw new Error(`Unable to load release years (${response.status})`);
  const {years} = await response.json();

  for (const selector of selectors) {
    const currentYear = Number(selector.dataset.leadersYear);
    selector.replaceChildren(...years.map(({year, label, path}) => {
      const option = new Option(label, path, false, year === currentYear);
      return option;
    }));
    selector.addEventListener("change", () => window.location.assign(selector.value));
  }
}

populateYearSelectors().catch((error) => console.error(error));
