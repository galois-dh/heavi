import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "Heavi",
  description: "Spatial computation platform",
};

// Dark-theme Clerk appearance shared across <SignIn/>, <SignUp/>, <UserButton/>.
const clerkAppearance = {
  variables: {
    colorPrimary: "#3b82f6",
    colorBackground: "#111827",
    colorText: "#f9fafb",
    colorInputBackground: "#1f2937",
    colorInputText: "#f9fafb",
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
