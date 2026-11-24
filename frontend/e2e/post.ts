import type { Page } from '@playwright/test'

/**
 * The post's own images. Each figure also holds the finalist strip's thumbnails, but those are decorative (empty alt),
 * so counting by the img role leaves them out.
 */
export function postImages(page: Page) {
  return page.locator('figure').getByRole('img')
}
