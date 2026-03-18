from PIL import Image, ImageFilter, ImageEnhance

def enhance_image(input_path, output_path):
    img = Image.open(input_path)
    
    # 1. Sharpening using Unsharp Mask
    # radius=2, percent=150, threshold=3 is a common starting point
    enhanced = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    
    # 2. Increase Contrast slightly
    enhancer = ImageEnhance.Contrast(enhanced)
    enhanced = enhancer.enhance(1.2)
    
    # 3. Increase Sharpness filter
    enhanced = enhanced.filter(ImageFilter.SHARPEN)
    
    enhanced.save(output_path, quality=95)
    print(f"Enhanced image saved to {output_path}")

if __name__ == '__main__':
    enhance_image('hyasic.jpeg', 'hyasic_enhanced.jpeg')
