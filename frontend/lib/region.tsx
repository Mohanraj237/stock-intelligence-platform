"use client";
import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

export type Region = "IN" | "US";

interface RegionCtx {
  region: Region;
  setRegion: (r: Region) => void;
  isUS: boolean;
  currencySymbol: string;
  formatCurrency: (n: number | null | undefined, opts?: { maxFrac?: number }) => string;
}

const RegionContext = createContext<RegionCtx>({
  region: "IN",
  setRegion: () => {},
  isUS: false,
  currencySymbol: "₹",
  formatCurrency: () => "—",
});

export function RegionProvider({ children }: { children: ReactNode }) {
  const [region, setRegionState] = useState<Region>("IN");

  useEffect(() => {
    const saved = localStorage.getItem("market_region") as Region | null;
    if (saved === "IN" || saved === "US") setRegionState(saved);
  }, []);

  const setRegion = (r: Region) => {
    setRegionState(r);
    localStorage.setItem("market_region", r);
  };

  const isUS = region === "US";
  const currencySymbol = isUS ? "$" : "₹";

  const formatCurrency = (n: number | null | undefined, opts: { maxFrac?: number } = {}): string => {
    if (n === null || n === undefined || Number.isNaN(n)) return "—";
    const maxFrac = opts.maxFrac ?? 2;
    return new Intl.NumberFormat(isUS ? "en-US" : "en-IN", {
      style: "currency",
      currency: isUS ? "USD" : "INR",
      maximumFractionDigits: maxFrac,
      minimumFractionDigits: 0,
    }).format(n);
  };

  return (
    <RegionContext.Provider value={{ region, setRegion, isUS, currencySymbol, formatCurrency }}>
      {children}
    </RegionContext.Provider>
  );
}

export function useRegion() {
  return useContext(RegionContext);
}
