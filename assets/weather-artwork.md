# Weather sprite sheet

Generated with the built-in image generation tool. The returned 1774×887 sheet was resized with Pillow to the packaged 240×120 RGB PNG at `src/soomfon_control/assets/weather-sprites.png`. Runtime crops eight 60×60 tiles in row-major order; no separate tile files or large source image are needed by the controller.

## Final prompt

Use case: stylized-concept. Create ONE compact weather background sprite sheet, 4 columns by 2 rows of exactly equal square tiles, no gutters or borders. Target 480x240 pixels if supported. Eight simple bold cartoon weather illustrations, readable when each is reduced to 60x60. Row 1 left to right: clear sun, partly cloudy sun, overcast clouds, fog with horizontal mist. Row 2: rain cloud with drops, snow cloud with flakes, thunderstorm cloud with lightning, icy rain cloud with drops and ice pellets. Each tile full bleed dark navy background with large colored central weather symbol, generous quiet top and bottom areas for white text to be overlaid later. Restrained deep colors and clean simple silhouettes, no text, letters, numbers, watermarks, grid lines, or tile labels. Exact regular 4x2 grid, each symbol contained within its tile.
