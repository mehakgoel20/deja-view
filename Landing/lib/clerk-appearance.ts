// Matches Clerk's prebuilt components to the site: black and white, small button
// radius, and flat buttons (Clerk's default primary button has a sheen overlay).
export const clerkAppearance = {
  variables: {
    colorPrimary: "#ffffff",
    colorPrimaryForeground: "#000000",
    colorBackground: "#0a0a0a",
    colorForeground: "#ffffff",
    borderRadius: "0.375rem",
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  },
  elements: {
    formButtonPrimary: {
      "&::after": { display: "none" },
    },
  },
};
