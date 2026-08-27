import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  webpack: (config) => {
    config.resolve.alias["@"] = path.resolve(process.cwd(), "src");
    return config;
  },
};

export default nextConfig;
