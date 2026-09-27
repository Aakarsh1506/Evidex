from pydantic import BaseModel, StrictStr


# Strict strings reject numbers; routes handle missing required fields.
class LoginBody(BaseModel):
    username: StrictStr | None = None
    password: StrictStr | None = None


class OfficerBody(LoginBody):
    name: StrictStr | None = None
    dob: StrictStr | None = None
    orgName: StrictStr | None = None


class PersonBody(BaseModel):
    personId: StrictStr | None = None


class CaseBody(BaseModel):
    caseId: StrictStr | None = None
