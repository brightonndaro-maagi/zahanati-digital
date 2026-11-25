"""Swahili / English for API messages. Clients send `Accept-Language: sw` (or `?lang=sw`); the default is
DEFAULT_LANGUAGE (English). Messages are written in English in the code and translated here, so a missing
translation falls back to English instead of failing."""
import re

from flask import current_app, has_request_context, request

SUPPORTED = ("sw", "en")


def get_lang(default=None):
    """The client's language (?lang= or Accept-Language); `default` (else DEFAULT_LANGUAGE) when it did not say."""
    fallback = default or current_app.config.get("DEFAULT_LANGUAGE", "en")
    if not has_request_context():
        return fallback
    lang = (request.args.get("lang") or "").lower()
    if lang in SUPPORTED:
        return lang
    for part in request.headers.get("Accept-Language", "").split(","):
        tag = part.split(";")[0].strip().lower()[:2]
        if tag in SUPPORTED:
            return tag
    return fallback


SW = {
    "Not found": "Haipatikani", "OK": "Sawa", "Saved": "Imehifadhiwa", "Updated": "Imesasishwa", "Deleted": "Imefutwa",
    "Published": "Imechapishwa", "Unpublished": "Imeondolewa kwenye uchapishaji", "Draft created": "Rasimu imetengenezwa",
    "Saved as draft: needs review before it goes live": "Imehifadhiwa kama rasimu: inahitaji ukaguzi kabla ya kuchapishwa",
    # --- auth / accounts
    "Login successful": "Umeingia kikamilifu", "Logged out": "Umetoka", "Token refreshed": "Tokeni imesasishwa",
    "Account created": "Akaunti imetengenezwa", "Account activated": "Akaunti imewashwa", "Account deactivated": "Akaunti imezimwa",
    "Invalid credentials": "Taarifa za kuingia si sahihi", "Invalid or expired code.": "Msimbo si sahihi au umeisha muda.",
    "Password has been reset": "Nenosiri limebadilishwa",
    "Password changed. All other sessions have been signed out.": "Nenosiri limebadilishwa. Vifaa vingine vimetolewa kwenye akaunti.",
    "Current password is incorrect": "Nenosiri la sasa si sahihi",
    "If the number can receive a code, an SMS has been sent.": "Ikiwa namba inaweza kupokea msimbo, SMS imetumwa.",
    "If the account exists, a reset code has been sent by SMS.": "Ikiwa akaunti ipo, msimbo wa kubadilisha nenosiri umetumwa kwa SMS.",
    "Code accepted. Please provide your full name to finish registration.": "Msimbo umekubaliwa. Tafadhali weka jina lako kamili kukamilisha usajili.",
    "A code has been sent to the new number.": "Msimbo umetumwa kwenye namba mpya.", "Phone number updated": "Namba ya simu imesasishwa",
    "Doctor registered. Awaiting administrator verification.": "Daktari amesajiliwa. Anasubiri uthibitisho wa admin.",
    "Pharmacy registered. Awaiting administrator approval.": "Famasia imesajiliwa. Inasubiri idhini ya admin.",
    "Phone number is already registered": "Namba ya simu tayari imesajiliwa", "Email is already registered": "Barua pepe tayari imesajiliwa",
    "Phone number or email is already registered": "Namba ya simu au barua pepe tayari imesajiliwa",
    "This number belongs to a professional account. Please log in with your password.": "Namba hii ni ya akaunti ya kitaalamu. Tafadhali ingia kwa nenosiri.",
    "This account has been deactivated. Contact support.": "Akaunti hii imezimwa. Wasiliana na msaada.",
    "Account not found or deactivated": "Akaunti haipatikani au imezimwa",
    "Account not found, deactivated, or the session has expired": "Akaunti haipatikani, imezimwa, au kipindi kimeisha",
    "Your session has expired. Please log in again.": "Kipindi chako kimeisha. Tafadhali ingia tena.",
    "Authentication required": "Unahitaji kuingia", "Invalid token": "Tokeni si sahihi", "Token has expired": "Tokeni imeisha muda",
    "Token has been revoked": "Tokeni imefutwa",
    "You do not have permission to access this resource": "Huna ruhusa ya kufikia rasilimali hii",
    "We could not send the SMS right now. Please try again shortly.": "Hatukuweza kutuma SMS sasa. Tafadhali jaribu tena baadaye.",
    "Request body must be a JSON object": "Mwili wa ombi lazima uwe kitu cha JSON", "Invalid JSON": "JSON si sahihi",
    "Validation failed": "Uthibitishaji umeshindwa", "Internal server error": "Hitilafu ya ndani ya seva",
    "This conflicts with an existing record": "Hii inagongana na rekodi iliyopo",
    "Search text must be at least 2 characters": "Maneno ya kutafuta lazima yawe angalau herufi 2",
    # --- profiles, doctors, pharmacies
    "Profile updated": "Wasifu umesasishwa", "Record added": "Rekodi imeongezwa", "Record updated": "Rekodi imesasishwa", "Record deleted": "Rekodi imefutwa",
    "Medical record not found": "Rekodi ya matibabu haipatikani", "Patient not found": "Mgonjwa hapatikani", "Patient profile not found": "Wasifu wa mgonjwa haupatikani",
    "Doctor not found": "Daktari hapatikani", "Doctor profile not found": "Wasifu wa daktari haupatikani", "Pharmacy not found": "Famasia haipatikani",
    "Pharmacy profile not found": "Wasifu wa famasia haupatikani", "User not found": "Mtumiaji hapatikani",
    "Doctor verified": "Daktari amethibitishwa", "Doctor rejected": "Daktari amekataliwa", "Pharmacy approved": "Famasia imeidhinishwa",
    "Pharmacy rejected": "Famasia imekataliwa", "Licence status updated": "Hali ya leseni imesasishwa",
    "Credential submitted": "Cheti kimewasilishwa", "Credential updated": "Cheti kimesasishwa", "Credential deleted": "Cheti kimefutwa",
    "Credential not found": "Cheti hakipatikani", "Specialisations updated": "Fani zimesasishwa", "Specialisation created": "Fani imeongezwa",
    "Specialisation updated": "Fani imesasishwa", "Specialisation deleted": "Fani imefutwa", "Specialisation not found": "Fani haipatikani",
    "Specialisation already exists": "Fani tayari ipo", "Specialisation name already exists": "Jina la fani tayari lipo",
    "Specialisation is assigned to doctors and cannot be deleted": "Fani imepewa madaktari na haiwezi kufutwa",
    "One or more specialisations do not exist": "Fani moja au zaidi hazipo",
    "Only verified doctors can perform this action": "Ni madaktari waliothibitishwa pekee wanaweza kufanya hivi",
    "Only verified doctors with an active licence can issue prescriptions": "Ni madaktari waliothibitishwa wenye leseni hai pekee wanaweza kuandika agizo la dawa",
    "Only verified doctors with an active licence can record clinical information": "Ni madaktari waliothibitishwa wenye leseni hai pekee wanaweza kuandika taarifa za matibabu",
    "Only verified doctors with an active licence can reply": "Ni madaktari waliothibitishwa wenye leseni hai pekee wanaweza kujibu",
    "Doctor has no licence credential to verify": "Daktari hana cheti cha leseni cha kuthibitisha",
    "This licence number is already registered to another doctor": "Namba hii ya leseni tayari imesajiliwa kwa daktari mwingine",
    "A pharmacy with this licence number is already registered": "Famasia yenye namba hii ya leseni tayari imesajiliwa",
    "Your pharmacy has not been approved yet": "Famasia yako bado haijaidhinishwa",
    "license_number is required for licence credentials": "Namba ya leseni inahitajika kwa vyeti vya leseni",
    "Workplace added": "Eneo la kazi limeongezwa", "Workplace updated": "Eneo la kazi limesasishwa", "Workplace removed": "Eneo la kazi limeondolewa",
    "Workplace not found": "Eneo la kazi halipatikani", "A current workplace cannot have an end_year": "Eneo la kazi la sasa haliwezi kuwa na mwaka wa kuishia",
    "end_year cannot be before start_year": "Mwaka wa kuishia hauwezi kuwa kabla ya mwaka wa kuanza",
    "Records entered by a doctor cannot be modified by the patient": "Rekodi zilizoandikwa na daktari haziwezi kubadilishwa na mgonjwa",
    "You are not authorised to access this patient's information": "Huna ruhusa ya kuona taarifa za mgonjwa huyu",
    # --- appointments
    "Availability updated": "Ratiba imesasishwa", "Appointment requested": "Miadi imeombwa", "Appointment rescheduled": "Miadi imebadilishwa muda",
    "Appointment accepted": "Miadi imekubaliwa", "Appointment rejected": "Miadi imekataliwa", "Appointment cancelled": "Miadi imeghairiwa",
    "Appointment completed": "Miadi imekamilika", "Appointment not found": "Miadi haipatikani",
    "This time slot is no longer available for the doctor": "Muda huu hauko wazi tena kwa daktari",
    "This time slot was just taken. Please choose another.": "Muda huu umechukuliwa sasa hivi. Tafadhali chagua mwingine.",
    "You already have an appointment that overlaps this time": "Tayari una miadi inayogongana na muda huu",
    "The doctor is not available at the requested time. Check the doctor's availability slots.": "Daktari hapatikani muda huo. Angalia muda ulio wazi.",
    "Past appointments cannot be rescheduled": "Miadi iliyopita haiwezi kubadilishwa", "The appointment time has already passed": "Muda wa miadi umeshapita",
    "An appointment can only be completed once it has started": "Miadi inaweza kukamilishwa baada ya kuanza tu",
    "This doctor is not currently available for appointments": "Daktari huyu hapokei miadi kwa sasa",
    "Date range must be between 1 and 14 days": "Kipindi cha tarehe lazima kiwe kati ya siku 1 na 14",
    # --- medicines / orders / prescriptions
    "Medicine added": "Dawa imeongezwa", "Medicine updated": "Dawa imesasishwa", "Medicine removed from sale": "Dawa imeondolewa kwenye mauzo",
    "Medicine not found": "Dawa haipatikani", "You already have a medicine with this name": "Tayari una dawa yenye jina hili",
    "Order placed": "Oda imewekwa", "Order cancelled": "Oda imeghairiwa", "Order collected": "Oda imechukuliwa", "Order marked as ready": "Oda imeandaliwa",
    "Order not found": "Oda haipatikani", "One or more medicines were not found": "Dawa moja au zaidi hazipatikani",
    "An order can only contain medicines from one pharmacy": "Oda inaweza kuwa na dawa za famasia moja tu",
    "Each medicine can appear only once in an order; increase its quantity instead": "Kila dawa inaweza kuwekwa mara moja kwenye oda; ongeza idadi badala yake",
    "Some medicines cannot be ordered": "Baadhi ya dawa haziwezi kuagizwa",
    "Some medicines are no longer available in the requested quantity": "Baadhi ya dawa hazipatikani tena kwa idadi iliyoombwa",
    "The order has not been paid yet": "Oda bado haijalipwa", "This order has already been paid": "Oda hii tayari imelipwa",
    "A payment for this order is already in progress": "Malipo ya oda hii tayari yanaendelea",
    "A payment is in progress for this order. Please wait for it to finish.": "Malipo ya oda hii yanaendelea. Tafadhali subiri yakamilike.",
    "A paid order cannot be cancelled here. Paid orders are cancelled through a refund.": "Oda iliyolipwa haiwezi kughairiwa hapa. Oda zilizolipwa zinaghairiwa kupitia kurejesha fedha.",
    "You cannot cancel this order": "Huwezi kughairi oda hii", "Only the pharmacy can do this": "Ni famasia pekee inayoweza kufanya hivi",
    "Prescription uploaded": "Agizo la daktari limepakiwa", "Prescription approved": "Agizo la daktari limeidhinishwa",
    "Prescription rejected": "Agizo la daktari limekataliwa", "Prescription attached": "Agizo la daktari limeambatishwa",
    "Prescription issued": "Agizo la dawa limeandikwa", "Prescription cancelled": "Agizo la dawa limefutwa", "Prescription not found": "Agizo la dawa halipatikani",
    "This order does not need a prescription": "Oda hii haihitaji agizo la daktari",
    "A prescription is already waiting for the pharmacy's review": "Agizo tayari linasubiri ukaguzi wa famasia",
    "A prescription is already attached or waiting for review": "Agizo tayari limeambatishwa au linasubiri ukaguzi",
    "The prescription has already been approved": "Agizo tayari limeidhinishwa", "The prescription has not been approved yet": "Agizo bado halijaidhinishwa",
    "There is no prescription waiting for review": "Hakuna agizo linalosubiri ukaguzi",
    "The prescription does not cover all medicines that need one": "Agizo halijumuishi dawa zote zinazohitaji agizo",
    "This prescription has been cancelled": "Agizo hili limefutwa", "This prescription has expired": "Agizo hili limeisha muda",
    "This prescription has already been used for another order": "Agizo hili tayari limetumika kwa oda nyingine",
    "The attached prescription was cancelled by the doctor": "Agizo lililoambatishwa limefutwa na daktari",
    "The issuing doctor is no longer verified": "Daktari aliyeandika agizo hajathibitishwa tena",
    "The prescription is already cancelled": "Agizo tayari limefutwa", "Only the issuing doctor can cancel a prescription": "Ni daktari aliyeandika agizo pekee anayeweza kulifuta",
    "Prescriptions can only be issued in an open consultation": "Maagizo yanaweza kuandikwa kwenye mazungumzo yaliyo wazi tu",
    "Attach the prescription as form field 'file'": "Ambatisha agizo kwenye sehemu ya fomu 'file'", "Only PDF, JPG or PNG files are accepted": "Faili za PDF, JPG au PNG pekee ndizo zinazokubaliwa",
    "The file is empty": "Faili ni tupu", "No prescription file is available for this order": "Hakuna faili la agizo kwa oda hii",
    "The stored file could not be read": "Faili lililohifadhiwa halikuweza kusomwa",
    "File encryption is not configured on the server": "Usimbaji wa faili haujawekwa kwenye seva", "File encryption is misconfigured on the server": "Usimbaji wa faili umewekwa vibaya kwenye seva",
    # --- payments
    "Payment started. Confirm it on your phone.": "Malipo yameanza. Thibitisha kwenye simu yako.", "Callback processed": "Taarifa ya malipo imepokelewa",
    "Refund recorded": "Urejeshaji fedha umerekodiwa", "Only paid orders can be refunded": "Oda zilizolipwa pekee ndizo zinaweza kurejeshewa fedha",
    "A valid mobile money phone number is required": "Namba halali ya simu ya malipo inahitajika",
    "The payment service is unavailable. Please try again shortly.": "Huduma ya malipo haipatikani. Tafadhali jaribu tena baadaye.",
    "Invalid callback signature": "Saini ya taarifa ya malipo si sahihi", "Unknown payment": "Malipo hayajulikani",
    "Amount does not match the payment": "Kiasi hakilingani na malipo", "Payment is already in a final state": "Malipo tayari yamekamilika",
    # --- consultations
    "Consultation started": "Mazungumzo yameanza", "Consultation closed": "Mazungumzo yamefungwa", "Message sent": "Ujumbe umetumwa",
    "Consultation not found": "Mazungumzo hayapatikani", "The consultation is already closed": "Mazungumzo tayari yamefungwa",
    "This consultation is closed. Start a new consultation to continue.": "Mazungumzo haya yamefungwa. Anzisha mazungumzo mapya kuendelea.",
    "This doctor is currently unavailable": "Daktari huyu hapatikani kwa sasa", "The message cannot be empty": "Ujumbe hauwezi kuwa tupu",
    # --- hedhi / content / admin
    "Period logged": "Hedhi imerekodiwa", "All your HEDHI data has been deleted": "Data yako yote ya HEDHI imefutwa", "Entry not found": "Rekodi haipatikani",
    "You already logged a period starting on this date": "Tayari ulirekodi hedhi inayoanza tarehe hii", "These dates overlap another logged period": "Tarehe hizi zinagongana na hedhi nyingine iliyorekodiwa",
    "You have reached the maximum number of logged periods. Delete old entries first.": "Umefikia idadi ya juu ya hedhi zilizorekodiwa. Futa za zamani kwanza.",
    "Content not found": "Maudhui hayapatikani", "Unpublish this content before deleting it": "Ondoa maudhui kwenye uchapishaji kabla ya kuyafuta",
    "Notification not found": "Arifa haipatikani", "You cannot deactivate your own account": "Huwezi kuzima akaunti yako mwenyewe",
    "You cannot deactivate the last active administrator": "Huwezi kuzima admin wa mwisho aliye hai", "The account is already deactivated": "Akaunti tayari imezimwa",
    "The account is already active": "Akaunti tayari iko hai",
    # --- validation (marshmallow)
    "'lat' must be within -90..90 and 'lon' within -180..180": "'lat' lazima iwe kati ya -90 na 90, na 'lon' kati ya -180 na 180",
    "Provide both 'lat' and 'lon' as numbers": "Weka 'lat' na 'lon' zote mbili kama namba",
    "Check the dates: the end cannot be before the start and a period lasts at most 14 days": "Hakiki tarehe: mwisho hauwezi kuwa kabla ya mwanzo na hedhi hudumu siku 14 kwa zaidi",
    "is_active must be true or false": "is_active lazima iwe true au false", "language must be 'sw' or 'en'": "language lazima iwe 'sw' au 'en'",
    "stage must be a number from 1 to 8": "stage lazima iwe namba kutoka 1 hadi 8",
    "Missing data for required field.": "Sehemu hii inahitajika.", "Not a valid string.": "Si maandishi sahihi.", "Not a valid integer.": "Si namba kamili sahihi.",
    "Not a valid number.": "Si namba sahihi.", "Not a valid boolean.": "Si thamani sahihi ya ndiyo/hapana.", "Not a valid date.": "Si tarehe sahihi.",
    "Not a valid datetime.": "Si tarehe na muda sahihi.", "Not a valid email address.": "Si barua pepe sahihi.", "Not a valid URL.": "Si kiungo sahihi.",
    "Not a valid UUID.": "Si kitambulisho sahihi.", "Field may not be null.": "Sehemu hii haiwezi kuwa tupu.", "Unknown field.": "Sehemu isiyojulikana.",
    "Not a valid list.": "Si orodha sahihi.", "Invalid input type.": "Aina ya ingizo si sahihi.", "Length must be at least 1.": "Lazima iwe na angalau kipengele 1.",
    "Password must be at least 8 characters and contain letters and digits.": "Nenosiri lazima liwe na angalau herufi 8 zenye herufi na tarakimu.",
    "This password is too easy to guess. Choose a different one.": "Nenosiri hili ni rahisi kubahatisha. Chagua jingine.",
    "Invalid Tanzanian mobile number. Use e.g. +255712345678 or 0712345678.": "Namba ya simu ya Tanzania si sahihi. Tumia mfano +255712345678 au 0712345678.",
    "Please enter your full name (first and last name).": "Tafadhali weka jina lako kamili (la kwanza na la mwisho).",
    "Code must be 6 digits.": "Msimbo lazima uwe na tarakimu 6.", "Minimum 2 characters.": "Angalau herufi 2.",
    "The start date cannot be in the future.": "Tarehe ya kuanza haiwezi kuwa ya baadaye.", "The end date cannot be before the start date.": "Tarehe ya kuisha haiwezi kuwa kabla ya kuanza.",
    "A period cannot last more than 14 days. Please check the dates.": "Hedhi haiwezi kudumu zaidi ya siku 14. Tafadhali hakiki tarehe.",
    "Date of birth cannot be in the future.": "Tarehe ya kuzaliwa haiwezi kuwa ya baadaye.", "Record date cannot be in the future.": "Tarehe ya rekodi haiwezi kuwa ya baadaye.",
}
PATTERNS = [
    (r"Invalid (status|role|payment_status) filter", lambda m: "Kichujio cha %s si sahihi" % m.group(1)),
    (r"'(\w+)' must be a date in YYYY-MM-DD format", lambda m: "'%s' lazima iwe tarehe ya muundo YYYY-MM-DD" % m.group(1)),
    (r"'(\w+)' must be a valid UUID", lambda m: "'%s' lazima iwe kitambulisho sahihi" % m.group(1)),
    (r"Cannot (\w+) an appointment that is (\w+)", lambda m: "Haiwezekani kufanya '%s' kwa miadi iliyo '%s'" % (m.group(1), m.group(2))),
    (r"Cannot (?:cancel|attach a prescription to|review a prescription for|upload a prescription for|mark) an order that is (\w+)(?: as ready)?", lambda m: "Haiwezekani kwa oda iliyo '%s'" % m.group(1)),
    (r"Cannot reschedule an appointment that is (\w+)", lambda m: "Miadi iliyo '%s' haiwezi kubadilishwa muda" % m.group(1)),
    (r"Only a ready order can be collected \(this one is (\w+)\)", lambda m: "Oda iliyo tayari pekee ndiyo inaweza kuchukuliwa (hii ni '%s')" % m.group(1)),
    (r"Please wait (\d+) seconds before requesting a new code\.", lambda m: "Tafadhali subiri sekunde %s kabla ya kuomba msimbo mpya." % m.group(1)),
    (r"Too many wrong attempts\. Try again in (\d+) (?:minute\(s\)|minutes)\.", lambda m: "Majaribio mengi yasiyo sahihi. Jaribu tena baada ya dakika %s." % m.group(1)),
    (r"Appointments must be booked at least (\d+) minutes ahead", lambda m: "Miadi lazima iwekwe angalau dakika %s kabla" % m.group(1)),
    (r"Appointments cannot be booked more than (\d+) days ahead", lambda m: "Miadi haiwezi kuwekwa zaidi ya siku %s kabla" % m.group(1)),
    (r"An order can contain at most (\d+) medicines", lambda m: "Oda inaweza kuwa na dawa zisizozidi %s" % m.group(1)),
    (r"Quantity per medicine cannot exceed (\d+)", lambda m: "Idadi ya kila dawa haiwezi kuzidi %s" % m.group(1)),
    (r"Refund must be between 1 and (\d+) TZS", lambda m: "Kiasi cha kurejesha lazima kiwe kati ya 1 na TZS %s" % m.group(1)),
    (r"The file is too large \(maximum (\d+) MB\)", lambda m: "Faili ni kubwa mno (kiwango cha juu ni MB %s)" % m.group(1)),
    (r"The message is too long \(maximum (\d+) characters\)", lambda m: "Ujumbe ni mrefu mno (kiwango cha juu ni herufi %s)" % m.group(1)),
    (r"Each window must be at least (\d+) minutes long", lambda m: "Kila kipindi lazima kiwe angalau dakika %s" % m.group(1)),
    (r"Overlapping availability windows on weekday (\d)", lambda m: "Vipindi vya ratiba vinagongana siku ya wiki %s" % m.group(1)),
    (r"You can list at most (\d+) workplaces", lambda m: "Unaweza kuorodhesha maeneo ya kazi yasiyozidi %s" % m.group(1)),
    (r"Payment network not supported\. Use one of: (.+)", lambda m: "Mtandao wa malipo haukubaliwi. Tumia mmoja wa: %s" % m.group(1)),
    (r"Shorter than minimum length (\d+)\.", lambda m: "Fupi kuliko urefu wa chini wa %s." % m.group(1)),
    (r"Longer than maximum length (\d+)\.", lambda m: "Ndefu kuliko urefu wa juu wa %s." % m.group(1)),
    (r"Length must be between (\d+) and (\d+)\.", lambda m: "Urefu lazima uwe kati ya %s na %s." % (m.group(1), m.group(2))),
    (r"Must be greater than or equal to (-?\d+) and less than or equal to (-?\d+)\.", lambda m: "Lazima iwe kati ya %s na %s." % (m.group(1), m.group(2))),
    (r"Must be greater than or equal to (-?\d+)\.", lambda m: "Lazima iwe angalau %s." % m.group(1)),
    (r"Must be less than or equal to (-?\d+)\.", lambda m: "Lazima isizidi %s." % m.group(1)),
    (r"Must be one of: (.+)\.", lambda m: "Lazima iwe mojawapo ya: %s." % m.group(1)),
    (r"Length must be between 1 and (\d+)\.", lambda m: "Lazima iwe na vipengele kati ya 1 na %s." % m.group(1)),
]
_COMPILED = [(re.compile(p + r"\Z"), f) for p, f in PATTERNS]


def tr(text, lang=None):
    if not isinstance(text, str):
        return text
    lang = lang or get_lang()
    if lang != "sw":
        return text
    if text in SW:
        return SW[text]
    for rx, fn in _COMPILED:
        m = rx.match(text)
        if m:
            return fn(m)
    return text


def tr_deep(value, lang=None):
    """Translate messages inside validation-error structures (dicts / lists of strings)."""
    if isinstance(value, str):
        return tr(value, lang)
    if isinstance(value, list):
        return [tr_deep(v, lang) for v in value]
    if isinstance(value, dict):
        return {k: tr_deep(v, lang) for k, v in value.items()}
    return value


# ---------------- notifications and SMS ----------------
NOTIFICATIONS_EN = {
    "order.created": "A new order has been received.", "order.expired": "Your order expired because it was not paid within 24 hours.",
    "order.ready": "Your order is ready for pickup.", "order.cancelled": "The order was cancelled.",
    "prescription.uploaded": "A prescription was uploaded. Please review it.", "prescription.approved": "Your prescription was approved. You can now pay.",
    "prescription.rejected": "Your prescription was rejected: {reason}. Please upload a new one.", "prescription.attached": "A doctor's electronic prescription was attached to the order.",
    "prescription.issued": "A doctor has written you a prescription.", "prescription.cancelled": "A doctor cancelled a prescription.",
    "payment.received": "Payment received. You can prepare the order.", "payment.paid": "Your payment was received.",
    "payment.failed": "The payment failed. You can try again.", "refund.due": "A late payment arrived for an order that cannot be fulfilled. Return the money to the customer.",
    "refund.recorded": "A refund of TZS {amount_tzs} was recorded.", "consultation.new": "You have a new message from a patient.",
    "consultation.message": "You have a new message.", "consultation.updated": "The doctor added treatment notes.", "consultation.closed": "The doctor closed the conversation.",
}


def notification_message(n, lang):
    if lang == "en" and n.type in NOTIFICATIONS_EN:
        try:
            return NOTIFICATIONS_EN[n.type].format(**(n.data or {}))
        except (KeyError, IndexError):
            return NOTIFICATIONS_EN[n.type].split("{")[0].strip()
    return n.message
