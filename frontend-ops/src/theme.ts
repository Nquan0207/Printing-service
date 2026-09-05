import { createTheme, type MantineColorsTuple } from "@mantine/core";

// RAKSUL's brand red, expanded to the 10 shades Mantine expects.
const raksul: MantineColorsTuple = [
  "#ffe9e9", "#ffd1d1", "#faa2a2", "#f57070", "#f14646",
  "#ef2c2c", "#ef1f1f", "#d51313", "#bf0a0f", "#a70009",
];

export const theme = createTheme({
  primaryColor: "raksul",
  colors: { raksul },
  defaultRadius: "md",
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Sans", "Noto Sans JP", sans-serif',
  headings: { fontWeight: "650" },
  components: {
    Card: { defaultProps: { withBorder: true, shadow: "none" } },
    Paper: { defaultProps: { withBorder: true } },
    Button: { defaultProps: { fw: 600 } },
  },
});
