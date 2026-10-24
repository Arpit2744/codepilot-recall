import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces .next/standalone for a small runtime Docker image.
  output: "standalone",
  // Contracts ship raw TypeScript; Next compiles them from the workspace package.
  transpilePackages: ["@codepilot/contracts"],
};

export default nextConfig;
