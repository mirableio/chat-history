// Main function to create the GitHub graph
function buildActivityGraph(parentElement, options) {
  var settings = Object.assign(
    {
      colorStep: 15,
      click: null,
      data: [],
    },
    options
  );

  var objTimestamp = {};

  function prettyNumber(number) {
    return number < 10 ? "0" + number.toString() : number.toString();
  }

  function processActivityList(activityByDay) {
    for (let [timestamp, count] of Object.entries(activityByDay)) {
      const date = new Date(timestamp);
      const displayDate = getDisplayDate(date);
  
      if (!objTimestamp[displayDate]) {
        objTimestamp[displayDate] = count;
      } else {
        objTimestamp[displayDate] += count;
      }
    }
  }
  
  function getDisplayDate(date) {
    // Helper function to format strings
    function formatString(str, args) {
        return str.replace(/{(\d+)}/g, function (match, number) {
        return typeof args[number] !== "undefined" ? args[number] : match;
        });
    }
  
    return formatString("{0}-{1}-{2}", [
      date.getFullYear(),
      prettyNumber(date.getMonth() + 1),
      prettyNumber(date.getDate()),
    ]);
  }

  function getCount(displayDate) {
    return objTimestamp[displayDate] || 0;
  }

  function getColor(count) {
      const colorRanges = ["#eeeeee", "#9be9a8", "#40c463", "#30a14e", "#216e39"];
      const index = count === 0 ? 0 : Math.min(Math.floor((count - 1) / settings.colorStep) + 1, colorRanges.length - 1);
      return colorRanges[index];
  }
  

  // Initiate the drawing
  function start() {
    processActivityList(settings.data);
    const wrapChart = parentElement;

    const radius = 2;
    const hoverColor = "#999";
    const clickCallback = settings.click;

    let startDate;
    startDate = new Date();
    startDate.setMonth(startDate.getMonth() - 12);
    startDate.setDate(startDate.getDate() + 1);

    let endDate = new Date(startDate);
    endDate.setMonth(endDate.getMonth() + 12);
    endDate.setDate(endDate.getDate() - 1);

    let loopHtml = "";
    const step = 13;

    let monthPosition = [];
    monthPosition.push({ monthIndex: startDate.getMonth(), x: 0 });
    let usingMonth = startDate.getMonth();

    let week = 0;
    let gx = week * step;
    let itemHtml = `<g transform="translate(${gx}, 0)">`;

    for (
      ;
      startDate.getTime() <= endDate.getTime();
      startDate.setDate(startDate.getDate() + 1)
    ) {
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
        itemHtml += `</g>`;
        loopHtml += itemHtml;

        week++;
        gx = week * step;
        itemHtml = `<g transform="translate(${gx}, 0)">`;
      }
    }

    if (itemHtml !== "") {
      itemHtml += `</g>`;
      loopHtml += itemHtml;
    }

    // Add month names to the graph
    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    for (let i = 0; i < monthPosition.length; i++) {
      const item = monthPosition[i];
      const monthName = monthNames[item.monthIndex];
      loopHtml += `<text x="${item.x}" y="-5" class="month">${monthName}</text>`;
    }

    // Add weekday labels
    loopHtml += `
            <text text-anchor="middle" class="wday" dx="-10" dy="23">M</text>
            <text text-anchor="middle" class="wday" dx="-10" dy="49">W</text>
            <text text-anchor="middle" class="wday" dx="-10" dy="75">F</text>
        `;

    // Finalize the SVG
    const wireHtml = `
          <svg width="720" height="110" viewBox="0 0 720 110" class="js-calendar-graph-svg">
            <g transform="translate(20, 20)">
              ${loopHtml}
            </g>
          </svg>
        `;

    wrapChart.innerHTML = wireHtml;

    // Attach event listeners for click and hover
    const dayElements = wrapChart.querySelectorAll(".day");
    dayElements.forEach((dayElement) => {
      dayElement.addEventListener("click", function () {
        if (clickCallback) {
          clickCallback(
            this.getAttribute("data-date"),
            parseInt(this.getAttribute("data-count"))
          );
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

    // Handle mouse events
    function mouseEnter(evt) {
      const targetRect = evt.target.getBoundingClientRect();
      const count = evt.target.getAttribute("data-count");
      const date = evt.target.getAttribute("data-date");

      if (count == 0) return;

      const text = `${count} messages on ${date}`;

      tooltip.innerHTML = text;
      tooltip.style.display = "block";
      tooltip.style.top = targetRect.top - tooltip.offsetHeight - 5 + "px";
      tooltip.style.left = targetRect.left - tooltip.offsetWidth / 2 + "px";
    }

    function mouseLeave(evt) {
      tooltip.style.display = "none";
    }

    // Attach event listeners for tooltips
    const rects = document.querySelectorAll(".day");
    rects.forEach(function (rect) {
      rect.addEventListener("mouseenter", mouseEnter);
      rect.addEventListener("mouseleave", mouseLeave);
    });
  }

  // Initialization
  start();
}

// ------------------------------------------------------------

function prepareBarChartData(activityData) {
  const today = new Date();
  const oneYearAgo = new Date();
  oneYearAgo.setFullYear(today.getFullYear() - 1);

  // Store counts by day, filling in zeros for missing days
  const allDates = {};
  let currentDate = new Date(oneYearAgo);
  while (currentDate <= today) {
      const dateStr = currentDate.toISOString().split("T")[0];
      allDates[dateStr] = 0;
      currentDate.setDate(currentDate.getDate() + 1);
  }

  // Fill in the counts for the days that have data
  Object.keys(activityData).forEach((dateStr) => {
      if (allDates.hasOwnProperty(dateStr)) {
          allDates[dateStr] = activityData[dateStr];
      }
  });

  const labels = Object.keys(allDates);
  const data = Object.values(allDates);

  // Prepare month labels
  const monthLabels = labels.map((dateStr) => {
      const dateObj = new Date(dateStr);
      return dateObj.getDate() === 1
          ? dateObj.toLocaleString("default", { month: "short" }) : "";
  });

  return {
      labels: labels,
      data: data,
      monthLabels: monthLabels,
  };
}

function buildActivityBarChart(data) {
  const preparedData = prepareBarChartData(data);

  const barCtx = document.getElementById("activity-bar-chart").getContext("2d");
  const myBarChart = new Chart(barCtx, {
      type: "bar",
      data: {
          labels: preparedData.labels,
          datasets: [
              {
                  label: "Messages",
                  data: preparedData.data,
                  // backgroundColor: "#216e39",
                  borderColor: "#30a14e",
                  borderWidth: 1,
              },
          ],
      },
      options: {
          aspectRatio: 4,
          plugins: {
              legend: {
                  display: false,
              },
          },
          scales: {
              x: {
                  grid: {
                      display: false, // Hide vertical grid lines
                  },
                  ticks: {
                      callback: function (value, index) {
                          // Only return the month label for the first day of each month
                          return preparedData.monthLabels[index];
                      },
                      autoSkip: false, // Display all labels
                      maxRotation: 0,
                      minRotation: 0,
                  },
              },
              y: {
                  beginAtZero: true,
              },
          },
      },
  });
}

// ------------------------------------------------------------
function buildAIStatsBarChart(data) {
    // Prepare data for the chart
    const labels = [];
    const inputCosts = [];
    const outputCosts = [];
    
    for (const entry of data) {
        labels.push(entry.month);
        inputCosts.push(entry.input / 100);  // Convert to dollars
        outputCosts.push(entry.output / 100);  // Convert to dollars
    }

    const mainContent = document.getElementById("main-content");
    mainContent.innerHTML = `
        <div>
          <h1 class="pt-10 pb-4 text-center text-xl">OpenAI estimated usage costs</h1>
          <canvas id="ai-cost-bar-chart"></canvas>
        </div>
    `;

    const monthLabels = labels.map((dateStr) => {
        const dateObj = new Date(dateStr);
        return dateObj.getDate() === 1
            ? dateObj.toLocaleString("default", { month: "short" }) : "";
    });

    // Create the chart
    const barCtx = document.getElementById('ai-cost-bar-chart').getContext('2d');
    const myBarChart = new Chart(barCtx, {
        type: 'bar',
        data: {
            labels: monthLabels,
            datasets: [
                {
                    label: 'Input $',
                    data: inputCosts,
                    minBarLength: 5,
                    backgroundColor: 'rgba(75, 192, 192, 0.5)',
                    borderColor: 'rgba(75, 192, 192, 1)',
                    borderWidth: 1
                },
                {
                    label: 'Output $',
                    data: outputCosts,
                    minBarLength: 5,
                    backgroundColor: 'rgba(255, 99, 132, 0.5)',
                    borderColor: 'rgba(255, 99, 132, 1)',
                    borderWidth: 1
                }
            ]
        },
        options: {
            aspectRatio: 4,
            plugins: {
                legend: {
                    display: false,
                },
                annotation: {
                  annotations: {
                    line1: {
                      type: 'line',
                      yMin: 20,
                      yMax: 20,
                      borderColor: 'rgb(255, 99, 132)',
                      borderWidth: 2,
                    }
                  }
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false // Hide vertical grid lines
                    },
                    stacked: true,
                },
                y: {
                    beginAtZero: true,
                    stacked: true,
                    ticks: {
                      callback: function(value, index, values) {
                          return '$' + value.toFixed(2);  // Format costs as dollar values
                      }
                  }
                }
            }
        }
    });
}