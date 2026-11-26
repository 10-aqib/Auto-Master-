import "@fontsource/roboto/latin-400.css";

/**
 * Attribution for Places content shown without a Google map. Google's rules: the text
 * "Google Maps" (not localised, not wrapped, unchanged capitalisation), Roboto 12–16px,
 * colour #5E5E5E/#1F1F1F (white on dark), inside the same container as the content.
 */
export function PlacesAttribution({ text, isMock }: { text: string; isMock: boolean }) {
  if (isMock) {
    return (
      <p className="text-xs font-medium text-amber-700 dark:text-amber-300" data-testid="attribution">
        {text}
      </p>
    );
  }
  return (
    <p
      translate="no"
      data-testid="attribution"
      className="whitespace-nowrap text-[14px] leading-none text-[#5E5E5E] dark:text-white"
      style={{ fontFamily: "Roboto, sans-serif" }}
    >
      {text}
    </p>
  );
}
