import { useQuery } from '@tanstack/react-query';

import { qk } from '../../../api/queryKeys';
import { portfolioApi } from '../../../api/services/portfolio.api';

export function usePortfolioAlbums(page = 1) {
  return useQuery({
    queryKey: qk.portfolio.albums(page),
    queryFn: () => portfolioApi.albums(page),
    staleTime: 5 * 60_000,
  });
}

export function usePortfolioImages(albumId?: number, page = 1) {
  return useQuery({
    queryKey: qk.portfolio.images(albumId, page),
    queryFn: () => portfolioApi.images(albumId, page),
    enabled: true,
    staleTime: 5 * 60_000,
  });
}
