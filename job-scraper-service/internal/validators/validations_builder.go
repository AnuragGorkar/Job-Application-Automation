package validator

func BuildChain() JobValidator {
	// Instantiate the validators
	wrapperValidator := NewWrapperValidator()
	timeWindowValidator := NewTimeWindowValidator()
	positionTitleValidator := NewPositionTitleValidator()
	urlValidator := NewURLValidator()
	employmentTypeValidator := NewEmploymentTypeValidator()
	locationValidator := NewLocationValidator()

	// 2. Declare the slice type and populate it
	validatorsList := []JobValidator{
		wrapperValidator,
		timeWindowValidator,
		positionTitleValidator,
		urlValidator,
		employmentTypeValidator,
		locationValidator,
	}

	// 3. Link the chain iteratively
	for i := 0; i < len(validatorsList)-1; i++ {
		validatorsList[i].SetNext(validatorsList[i+1])
	}

	return validatorsList[0]
}
