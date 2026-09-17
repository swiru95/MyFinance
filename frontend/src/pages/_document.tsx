import { Html, Head, Main, NextScript } from "next/document";
import { THEME_KEY } from "@/lib/theme";

// Runs before first paint so the correct palette is in place immediately -
// without this the page flashes light before React hydrates.
const noFlashScript = `
(function () {
  try {
    var stored = localStorage.getItem(${JSON.stringify(THEME_KEY)}) || "system";
    var dark =
      stored === "dark" ||
      (stored === "system" &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  } catch (e) {}
})();
`;

export default function Document() {
  return (
    <Html lang="en">
      <Head />
      <body>
        <script dangerouslySetInnerHTML={{ __html: noFlashScript }} />
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
