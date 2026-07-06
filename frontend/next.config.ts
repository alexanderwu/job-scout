import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The API's address is read at request time in lib/api.ts via
  // NEXT_PUBLIC_API_URL; no build-time config needed here yet.
};

export default nextConfig;
