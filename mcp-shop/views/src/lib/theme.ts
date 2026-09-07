import { createTheme, type MantineColorsTuple } from "@mantine/core";

// The same RAKSUL red used by frontend-ops, chat-ui and the mcp-ops Views, so
// a panel rendered inside a chat matches the apps it is a window onto.
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
  fontSizes: { sm: "13px", md: "14px" },
  headings: { fontWeight: "650" },
  components: {
    Card: { defaultProps: { withBorder: true, shadow: "none" } },
    Paper: { defaultProps: { withBorder: true } },
    Button: { defaultProps: { fw: 600 } },
  },
});
