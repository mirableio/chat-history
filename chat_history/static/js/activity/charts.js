let activityBarChartInstance = null;

export function buildActivityGraph(parentElement, options) {
  const settings = Object.assign(
    {
      colorStep: 15,
      click: null,
      data: [],
      colorRanges: ["#eeeeee", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
      year: null,
    },
    options
  );

  const objTimestamp = {};

  function prettyNumber(number) {
    return number < 10 ? `0${number}` : String(number);
  }

  function processActivityList(activityByDay) {
    for (const [timestamp, count] of Object.entries(activityByDay)) {
      let displayDate;
      if (/^\d{4}-\d{2}-\d{2}$/.test(String(timestamp))) {
        displayDate = String(timestamp);
      } else {
        const date = new Date(timestamp);
        displayDate = getDisplayDate(date);
      }

      if (!objTimestamp[displayDate]) {
        objTimestamp[displayDate] = count;
      } else {
        objTimestamp[displayDate] += count;
      }
    }
  }

  function getDisplayDate(date) {
    return `${date.getFullYear()}-${prettyNumber(date.getMonth() + 1)}-${prettyNumber(date.getDate())}`;
  }

  function getCount(displayDate) {
    return objTimestamp[displayDate] || 0;
  }

  function getColor(count) {
    const colorRanges = settings.colorRanges;
    const index =
      count === 0
        ? 0
        : Math.min(Math.floor((count - 1) / settings.colorStep) + 1, colorRanges.length - 1);
    return colorRanges[index];
  }

  function start() {
    processActivityList(settings.data);
    const wrapChart = parentElement;

    const radius = 2;
    const hoverColor = "#999";
    const clickCallback = settings.click;

    let startDate;
    let endDate;
    if (Number.isInteger(settings.year)) {
      startDate = new Date(settings.year, 0, 1);
      endDate = new Date(settings.year, 11, 31);
    } else {
      startDate = new Date();
      startDate.setMonth(startDate.getMonth() - 12);
      startDate.setDate(startDate.getDate() + 1);

      endDate = new Date(startDate);
      endDate.setMonth(endDate.getMonth() + 12);
      endDate.setDate(endDate.getDate() - 1);
    }

    let loopHtml = "";
    const step = 13;

    const monthPosition = [];
    monthPosition.push({ monthIndex: startDate.getMonth(), x: 0 });
    let usingMonth = startDate.getMonth();

    let week = 0;
    let gx = week * step;
    let itemHtml = `<g transform="translate(${gx}, 0)">`;

    for (; startDate.getTime() <= endDate.getTime(); startDate.setDate(startDate.getDate() + 1)) {
      const monthInDay = startDate.getMonth();
      const dataDate = getDisplayDate(startDate);

      if (startDate.getDay() === 0 && monthInDay !== usingMonth) {
        usingMonth = monthInDay;
        monthPosition.push({ monthIndex: usingMonth, x: gx });
      }

      const count = getCount(dataDate);
      const color = getColor(count);

      const y = startDate.getDay() * step;
      itemHtml += `<rect class="day" width="11" height="11" y="${y}" fill="${color}" data-count="${count}" data-date="${dataDate}" rx="${radius}" ry="${radius}"/>`;

      if (startDate.getDay() === 6) {
        itemHtml += "</g>";
        loopHtml += itemHtml;

        week += 1;
        gx = week * step;
        itemHtml = `<g transform="translate(${gx}, 0)">`;
      }
    }

    if (itemHtml !== "") {
      itemHtml += "</g>";
      loopHtml += itemHtml;
    }

    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const minMonthGap = 30;
    for (let i = 0; i < monthPosition.length; i += 1) {
      const item = monthPosition[i];
      const nextX = i + 1 < monthPosition.length ? monthPosition[i + 1].x : Infinity;
      if (nextX - item.x < minMonthGap) {
        continue;
      }
      const monthName = monthNames[item.monthIndex];
      loopHtml += `<text x="${item.x}" y="-5" class="month">${monthName}</text>`;
    }

    loopHtml += `
            <text text-anchor="middle" class="wday" dx="-10" dy="23">M</text>
            <text text-anchor="middle" class="wday" dx="-10" dy="49">W</text>
            <text text-anchor="middle" class="wday" dx="-10" dy="75">F</text>
        `;

    const wireHtml = `
          <svg width="720" height="110" viewBox="0 0 720 110" class="js-calendar-graph-svg">
            <g transform="translate(20, 20)">
              ${loopHtml}
            </g>
          </svg>
        `;

    wrapChart.innerHTML = wireHtml;

    const dayElements = wrapChart.querySelectorAll(".day");
    dayElements.forEach((dayElement) => {
      dayElement.addEventListener("click", function () {
        if (clickCallback) {
          clickCallback(this.getAttribute("data-date"), parseInt(this.getAttribute("data-count"), 10));
        }
      });

      dayElement.addEventListener("mouseenter", function () {
        this.setAttribute("style", `stroke-width: 1; stroke: ${hoverColor}`);
      });

      dayElement.addEventListener("mouseleave", function () {
        this.setAttribute("style", "stroke-width: 0");
      });
    });

    let tooltip;
    if (!document.querySelector(".svg-tip")) {
      tooltip = document.createElement("div");
      tooltip.className = "svg-tip";
      tooltip.style.display = "none";
      document.body.appendChild(tooltip);
    } else {
      tooltip = document.querySelector(".svg-tip");
    }

    function mouseEnter(evt) {
      const targetRect = evt.target.getBoundingClientRect();
      const count = evt.target.getAttribute("data-count");
      const date = evt.target.getAttribute("data-date");

      if (count === "0") {
        return;
      }

      tooltip.innerHTML = `${count} messages on ${date}`;
      tooltip.style.display = "block";
      tooltip.style.top = `${targetRect.top - tooltip.offsetHeight - 5}px`;
      tooltip.style.left = `${targetRect.left - tooltip.offsetWidth / 2}px`;
    }

    function mouseLeave() {
      tooltip.style.display = "none";
    }

    const rects = document.querySelectorAll(".day");
    rects.forEach((rect) => {
      rect.addEventListener("mouseenter", mouseEnter);
      rect.addEventListener("mouseleave", mouseLeave);
    });
  }

  start();
}

function prepareBarChartData(activityData, year) {
  const allDates = {};
  let startDate;
  let endDate;

  if (Number.isInteger(year)) {
    startDate = new Date(year, 0, 1);
    endDate = new Date(year, 11, 31);
  } else {
    endDate = new Date();
    startDate = new Date();
    startDate.setFullYear(endDate.getFullYear() - 1);
  }

  const currentDate = new Date(startDate);
  while (currentDate <= endDate) {
    const dateStr = currentDate.toISOString().split("T")[0];
    allDates[dateStr] = 0;
    currentDate.setDate(currentDate.getDate() + 1);
  }

  Object.keys(activityData).forEach((dateStr) => {
    if (Object.prototype.hasOwnProperty.call(allDates, dateStr)) {
      allDates[dateStr] = activityData[dateStr];
    }
  });

  const labels = Object.keys(allDates);
  const data = Object.values(allDates);

  const monthLabels = labels.map((dateStr) => {
    const dateObj = new Date(dateStr);
    return dateObj.getDate() === 1 ? dateObj.toLocaleString("default", { month: "short" }) : "";
  });

  return { labels, data, monthLabels };
}

function destroyActivityBarChart() {
  if (activityBarChartInstance) {
    activityBarChartInstance.destroy();
    activityBarChartInstance = null;
  }
}

export function buildActivityBarChart(data, year) {
  const preparedData = prepareBarChartData(data, year);
  const barCanvas = document.getElementById("activity-bar-chart");
  if (!barCanvas) {
    return;
  }
  const barCtx = barCanvas.getContext("2d");

  destroyActivityBarChart();
  activityBarChartInstance = new Chart(barCtx, {
    type: "bar",
    data: {
      labels: preparedData.labels,
      datasets: [
        {
          label: "Messages",
          data: preparedData.data,
          borderColor: "#30a14e",
          backgroundColor: "rgba(48, 161, 78, 0.35)",
          borderWidth: 1,
        },
      ],
    },
    options: {
      aspectRatio: 4,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            callback(value, index) {
              return preparedData.monthLabels[index];
            },
            autoSkip: false,
            maxRotation: 0,
            minRotation: 0,
          },
        },
        y: { beginAtZero: true },
      },
    },
  });
}

function defaultTheme() {
  return {
    barBg: "rgba(48, 161, 78, 0.35)",
    barBorder: "#30a14e",
  };
}

export function buildActivityBarChartByProvider(providerSeries, year, resolveProviderTheme) {
  const providers = Object.keys(providerSeries);
  if (providers.length === 0) {
    buildActivityBarChart({}, year);
    return;
  }

  const basePrepared = prepareBarChartData(providerSeries[providers[0]], year);
  const datasets = providers.map((provider, index) => {
    const prepared = prepareBarChartData(providerSeries[provider], year);
    const theme =
      typeof resolveProviderTheme === "function"
        ? resolveProviderTheme(provider, index)
        : defaultTheme();
    const safeTheme = { ...defaultTheme(), ...(theme || {}) };
    return {
      label: provider,
      data: prepared.data,
      borderColor: safeTheme.barBorder,
      backgroundColor: safeTheme.barBg,
      borderWidth: 1,
    };
  });

  const barCanvas = document.getElementById("activity-bar-chart");
  if (!barCanvas) {
    return;
  }
  const barCtx = barCanvas.getContext("2d");
  destroyActivityBarChart();

  activityBarChartInstance = new Chart(barCtx, {
    type: "bar",
    data: {
      labels: basePrepared.labels,
      datasets,
    },
    options: {
      aspectRatio: 4,
      plugins: { legend: { display: true } },
      scales: {
        x: {
          grid: { display: false },
          stacked: true,
          ticks: {
            callback(value, index) {
              return basePrepared.monthLabels[index];
            },
            autoSkip: false,
            maxRotation: 0,
            minRotation: 0,
          },
        },
        y: { beginAtZero: true, stacked: true },
      },
    },
  });
}

export function buildAIStatsBarChart(data) {
  const mainContent = document.getElementById("main-content");
  if (!data || data.length === 0) {
    mainContent.innerHTML = `
            <div class="pt-10 text-center">No token statistics available.</div>
        `;
    return;
  }

  const labels = [];
  const inputTokens = [];
  const outputTokens = [];
  for (const entry of data) {
    labels.push(`${entry.provider}:${entry.model}`);
    inputTokens.push(entry.input_tokens || 0);
    outputTokens.push(entry.output_tokens || 0);
  }

  mainContent.innerHTML = `
        <div>
          <h1 class="pt-10 pb-4 text-center text-xl">Token usage by provider and model</h1>
          <canvas id="ai-cost-bar-chart"></canvas>
        </div>
    `;

  const barCtx = document.getElementById("ai-cost-bar-chart").getContext("2d");
  new Chart(barCtx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Input tokens",
          data: inputTokens,
          minBarLength: 5,
          backgroundColor: "rgba(75, 192, 192, 0.5)",
          borderColor: "rgba(75, 192, 192, 1)",
          borderWidth: 1,
        },
        {
          label: "Output tokens",
          data: outputTokens,
          minBarLength: 5,
          backgroundColor: "rgba(255, 99, 132, 0.5)",
          borderColor: "rgba(255, 99, 132, 1)",
          borderWidth: 1,
        },
      ],
    },
    options: {
      aspectRatio: 3,
      plugins: {
        legend: {
          display: true,
        },
      },
      scales: {
        x: {
          grid: {
            display: false,
          },
          stacked: true,
          ticks: {
            autoSkip: false,
            maxRotation: 65,
            minRotation: 65,
          },
        },
        y: {
          beginAtZero: true,
          stacked: true,
          ticks: {
            callback(value) {
              return value.toLocaleString();
            },
          },
        },
      },
    },
  });
}
