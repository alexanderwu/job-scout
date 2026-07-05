import Link from "next/link";

export function NavBar() {
  return (
    <header className="border-b border-neutral-200 dark:border-neutral-800">
      <nav className="mx-auto flex max-w-3xl items-center gap-6 px-4 py-4">
        <Link href="/" className="font-semibold">
          Job Scout
        </Link>
        <Link
          href="/"
          className="text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
        >
          Matches
        </Link>
        <Link
          href="/saved"
          className="text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
        >
          Saved
        </Link>
        <Link
          href="/skill-gap"
          className="text-sm text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
        >
          Skill Gap
        </Link>
      </nav>
    </header>
  );
}
