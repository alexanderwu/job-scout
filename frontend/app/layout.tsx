import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Job Scout",
  description: "Ranked job matches with visible reasoning.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <Link href="/" className="brand">
            Job&nbsp;Scout
          </Link>
          <nav>
            <Link href="/">Profiles</Link>
            <Link href="/jobs">Jobs</Link>
            <Link href="/tracker">Tracker</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
