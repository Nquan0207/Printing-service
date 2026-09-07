import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Shared with frontend-ops, chat-ui and mcp-shop: a panel rendered inside a
// chat should match the apps it is a window onto.
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
  // Views sit inside a conversation, so they run a step smaller than the apps.
  fontSizes: { xs: "10px", sm: "11px", md: "13px", lg: "15px" },
  headings: { fontWeight: "650", sizes: { h1: { fontSize: "15px" } } },
  components: {
    Paper: { defaultProps: { withBorder: true } },
    Table: { defaultProps: { verticalSpacing: "xs", horizontalSpacing: "sm", fz: "sm" } },
  },
});
