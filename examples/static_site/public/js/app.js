// genro-asgi Static Site JavaScript

document.addEventListener('DOMContentLoaded', function() {
    console.log('genro-asgi static site loaded!');

    // Contact form handling
    const contactForm = document.getElementById('contactForm');
    if (contactForm) {
        contactForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const name = document.getElementById('name').value;
            const email = document.getElementById('email').value;
            const message = document.getElementById('message').value;

            // Simulate form submission
            console.log('Form submitted:', { name, email, message });

            const result = document.getElementById('formResult');
            result.textContent = 'Thank you, ' + name + '! Your message has been received.';
            result.className = 'form-result success';

            contactForm.reset();
        });
    }

    // Add smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        });
    });
});
