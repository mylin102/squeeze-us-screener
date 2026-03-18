from PIL import Image

def upscale_4x(input_path, output_path):
    try:
        img = Image.open(input_path)
        original_size = img.size
        new_size = (original_size[0] * 4, original_size[1] * 4)
        
        print(f"Original size: {original_size}")
        print(f"Target 4x size: {new_size}")
        
        # Use Lanczos resampling for high-quality downsampling/upsampling
        upscaled_img = img.resize(new_size, resample=Image.Resampling.LANCZOS)
        
        # Save with high quality
        upscaled_img.save(output_path, quality=95, subsampling=0)
        print(f"Successfully saved 4x upscaled image to {output_path}")
        
    except Exception as e:
        print(f"Error upscaling image: {e}")

if __name__ == '__main__':
    upscale_4x('hyasic.jpeg', 'hyasic_4x_lanczos.jpeg')
