import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "Heavi",
  description: "Spatial computation platform",
};

// Dark-theme Clerk appearance shared across <SignIn/>, <SignUp/>, <UserButton/>.
// colorNeutral must be a LIGHT base: Clerk derives the UserButton dropdown's
// action-button text, secondary text, icons, and borders from it, so a dark
// default renders dark-on-dark (invisible) on our dark surface. A light base
// produces visible neutral shades. Tones match the site's zinc palette.
const clerkAppearance = {
  variables: {
    colorPrimary: "#3b82f6",
    colorBackground: "#18181b", // zinc-900 — card/popover surface
    colorText: "#f9fafb", // zinc-50 — primary text
    colorTextSecondary: "#a1a1aa", // zinc-400 — emails, labels, hints
    colorNeutral: "#fafafa", // light base for derived neutral shades on dark bg
    colorInputBackground: "#27272a", // zinc-800
    colorInputText: "#f9fafb",
  },
  // Target the UserButton popover identifier (name/email) and action buttons
  // explicitly. The email at the top of the dropdown is the user-preview
  // identifier, which colorNeutral does not reliably lighten. globals.css also
  // forces these via .cl-* selectors as a belt-and-suspenders fallback.
  elements: {
    userButtonPopoverCard: { backgroundColor: "#18181b", borderColor: "#27272a" },
    userButtonPopoverActionButton: { color: "#f9fafb" },
    userPreviewMainIdentifier: { color: "#f9fafb" }, // zinc-50
    userPreviewSecondaryIdentifier: { color: "#d4d4d8" }, // zinc-300
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <ClerkProvider appearance={clerkAppearance} afterSignOutUrl="/">
      <html lang="en" className="h-full">
        <body className="h-full bg-zinc-950 text-zinc-100 antialiased">{children}</body>
      </html>
    </ClerkProvider>
  );
}
