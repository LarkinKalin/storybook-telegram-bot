-- TG.7.4.01.A — allow scheduling step images before asset generation

ALTER TABLE session_images
  ALTER COLUMN asset_id DROP NOT NULL;
