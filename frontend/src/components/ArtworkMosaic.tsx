export function ArtworkMosaic({ artworkUrls, label }: { artworkUrls: string[]; label: string }) {
  return (
    <div className="artwork-mosaic" role="img" aria-label={label}>
      {artworkUrls.map((url, index) => (
        <img key={`${url}-${index}`} src={url} alt="" />
      ))}
    </div>
  );
}
