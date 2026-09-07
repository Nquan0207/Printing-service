import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MantineProvider } from "@mantine/core";

import "@mantine/core/styles.css";

import Storefront from "../views/Storefront";
import { theme } from "../lib/theme";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* The iframe follows the host's colour scheme rather than forcing one. */}
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Storefront />
    </MantineProvider>
  </StrictMode>,
);
