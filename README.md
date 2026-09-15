# ff-gen-100 - FreeFire Generator clone (ID region default)
Endpoints:
- /gen?name=Sam&count=5&region=ID&password_prefix=GG&ghost=false&detect_rare=true
- /bulk?name=Sam&count=100&region=ID -> 100x paralel, 6-10 detik
- /patterns -> 12 rare regex
Deploy: vercel --prod
