import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "CodePilot Recall",
    template: "%s · CodePilot Recall",
  },
  description:
    "Connect your Codeforces handle, keep your original solve dates, and revise problems with an adaptive spaced-repetition schedule.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-dvh bg-slate-950 text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
