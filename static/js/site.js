// The site works without this file. It only runs the Play button on a recording:
// the page shows a still frame, and the animation is fetched when Play is pressed.

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
