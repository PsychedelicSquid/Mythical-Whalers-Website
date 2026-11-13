// The site works without this file. It adds three conveniences:
// the Play button on a recording, the filter box on a Wiki category page,
// and the search box on the Wiki's front page.

// A recording shows a still frame. The animation is fetched when Play is pressed.
document.addEventListener("click", function (event) {
  var button = event.target.closest("[data-play]");
  if (!button) {
    return;
  }
  var picture = button.closest(".player").querySelector("img");
  if (button.getAttribute("aria-pressed") === "true") {
    picture.src = picture.getAttribute("data-still");
    button.setAttribute("aria-pressed", "false");
    button.textContent = "Play";
  } else {
    picture.setAttribute("data-still", picture.getAttribute("src"));
    picture.src = button.getAttribute("data-play");
    button.setAttribute("aria-pressed", "true");
    button.textContent = "Stop";
  }
});

// A category page's filter box hides the entries whose name does not contain
// what was typed.
function filterCards(box) {
  var wanted = box.value.trim().toLowerCase();
  var cards = document.querySelectorAll(box.getAttribute("data-filter") + " [data-name]");
  var shown = 0;
  for (var i = 0; i < cards.length; i++) {
    var matches = cards[i].getAttribute("data-name").indexOf(wanted) !== -1;
    cards[i].hidden = !matches;
    if (matches) {
      shown += 1;
    }
  }
  var none = document.querySelector(box.getAttribute("data-none"));
  if (none) {
    none.hidden = shown > 0;
  }
}

// The Wiki's search box lists entries from every category. The list of names
// is fetched once, the first time something is typed.
var searchIndex = null;

function showResults(box) {
  var results = document.querySelector(box.getAttribute("data-results"));
  var wanted = box.value.trim().toLowerCase();
  results.textContent = "";
  if (wanted === "" || searchIndex === null) {
    results.hidden = true;
    return;
  }
  // Names that start with what was typed come first.
  var starts = [];
  var contains = [];
  for (var i = 0; i < searchIndex.length; i++) {
    var position = searchIndex[i].n.toLowerCase().indexOf(wanted);
    if (position === 0) {
      starts.push(searchIndex[i]);
    } else if (position > 0) {
      contains.push(searchIndex[i]);
    }
  }
  var found = starts.concat(contains).slice(0, 12);
  for (var j = 0; j < found.length; j++) {
    var link = document.createElement("a");
    link.className = "card tip";
    link.href = found[j].u;
    var name = document.createElement("h3");
    name.textContent = found[j].n;
    var category = document.createElement("p");
    category.className = "dim";
    category.textContent = found[j].c;
    link.appendChild(name);
    link.appendChild(category);
    results.appendChild(link);
  }
  if (found.length === 0) {
    var none = document.createElement("p");
    none.className = "dim";
    none.textContent = "Nothing in the Wiki has that in its name.";
    results.appendChild(none);
  }
  results.hidden = false;
}

document.addEventListener("input", function (event) {
  var box = event.target;
  if (box.matches("[data-filter]")) {
    filterCards(box);
    return;
  }
  if (box.matches("[data-search]")) {
    if (searchIndex !== null) {
      showResults(box);
      return;
    }
    fetch(box.getAttribute("data-search"))
      .then(function (response) { return response.json(); })
      .then(function (rows) {
        searchIndex = rows;
        showResults(box);
      });
  }
});
