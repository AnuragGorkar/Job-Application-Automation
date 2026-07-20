package validator

type ValidationsBuilder struct{}

func BuildChain() JobValidator {
	locationValidator := NewLocationValidator()
	employmentTypeValidator := NewEmploymentTypeValidator()
	positionTitleValidator := NewPositionTitleValidator()
	timeWindowValidator := NewTimeWindowValidator()
	urlValidator := NewURLValidator()

	locationValidator.SetNext(employmentTypeValidator)
	employmentTypeValidator.SetNext(positionTitleValidator)
	positionTitleValidator.SetNext(timeWindowValidator)
	timeWindowValidator.SetNext(urlValidator)
	urlValidator.SetNext(nil)

	return locationValidator
}
