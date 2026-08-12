import { useEffect, useState } from 'react';

/**
 * Delay a rapidly-changing value.
 *
 * Without this, typing "wedding" in the search box fires seven API requests
 * — and because responses can arrive out of order, the list can end up
 * showing results for "weddin". Debouncing collapses the burst into one
 * request for the final value.
 */
export function useDebounce<T>(value: T, delay = 400): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    // Clearing on every change is what makes this a debounce rather than a
    // throttle: the timer only fires once the value has been still for
    // `delay` milliseconds.
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
